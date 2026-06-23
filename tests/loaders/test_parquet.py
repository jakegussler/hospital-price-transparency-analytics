"""Tests for hpt.loaders.parquet — BronzeWriter."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from hpt.loaders.parquet import BronzeWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_schema() -> dict[str, pl.DataType]:
    return {"id": pl.Utf8, "value": pl.Float64}


def _make_df(rows: int = 3) -> pl.DataFrame:
    return pl.DataFrame(
        {"id": [f"r{i}" for i in range(rows)], "value": [float(i) for i in range(rows)]},
        schema=_simple_schema(),
    )


def _part_path(bronze_root: Path, table: str, snapshot_id: str, part: int = 0) -> Path:
    return bronze_root / table / f"snapshot_id={snapshot_id}" / f"part-{part:03d}.parquet"


# ---------------------------------------------------------------------------
# Basic write behaviour
# ---------------------------------------------------------------------------


class TestWriteBatch:
    def test_creates_parquet_file(self, tmp_path):
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": _make_df()})

        assert _part_path(tmp_path, "charges", "snap-1").exists()

    def test_empty_df_materialized_as_zero_row_file(self, tmp_path):
        # A table emitted only as an empty DataFrame is still materialized as a
        # zero-row Parquet on close so its partition directory always exists and
        # downstream read_parquet globs never fail on an absent optional table.
        empty = pl.DataFrame(schema=_simple_schema())
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": empty})

        path = _part_path(tmp_path, "charges", "snap-1")
        assert path.exists()
        table = pq.read_table(path)
        assert table.num_rows == 0
        # File carries the declared schema (snapshot_id is added by the reader
        # from the Hive partition path, so only assert the data columns).
        assert {"id", "value"} <= set(table.column_names)

    def test_empty_table_not_written_when_table_also_has_rows(self, tmp_path):
        # An empty batch followed by a populated batch for the same table must
        # not produce a spurious extra empty part file.
        empty = pl.DataFrame(schema=_simple_schema())
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": empty})
            writer.write_batch({"charges": _make_df()})

        assert _part_path(tmp_path, "charges", "snap-1").exists()
        # No second part file from the empty-table fallback.
        assert not _part_path(tmp_path, "charges", "snap-1", part=1).exists()
        table = pq.read_table(_part_path(tmp_path, "charges", "snap-1"))
        assert table.num_rows == 3

    def test_multiple_tables_separate_dirs(self, tmp_path):
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": _make_df(), "codes": _make_df()})

        assert _part_path(tmp_path, "charges", "snap-1").exists()
        assert _part_path(tmp_path, "codes", "snap-1").exists()

    def test_hive_partition_path_structure(self, tmp_path):
        with BronzeWriter(tmp_path, "my-snap") as writer:
            writer.write_batch({"my_table": _make_df()})

        expected = tmp_path / "my_table" / "snapshot_id=my-snap" / "part-000.parquet"
        assert expected.exists()

    def test_multiple_batches_append_same_part(self, tmp_path):
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": _make_df(2)})
            writer.write_batch({"charges": _make_df(3)})

        part = _part_path(tmp_path, "charges", "snap-1")
        assert part.exists()
        # part-001 should NOT exist (no roll happened)
        assert not _part_path(tmp_path, "charges", "snap-1", part=1).exists()

        table = pq.read_table(str(part))
        assert table.num_rows == 5


# ---------------------------------------------------------------------------
# Part rolling
# ---------------------------------------------------------------------------


class TestPartRolling:
    def test_roll_creates_new_part_file(self, tmp_path):
        threshold = BronzeWriter.PART_ROW_THRESHOLD
        writer = BronzeWriter(tmp_path, "snap-1")

        batch = _make_df(threshold)
        writer.write_batch({"charges": batch})
        # At threshold: roll should have happened
        writer.write_batch({"charges": _make_df(1)})
        writer.close()

        assert _part_path(tmp_path, "charges", "snap-1", part=0).exists()
        assert _part_path(tmp_path, "charges", "snap-1", part=1).exists()

    def test_total_row_counts_accumulated_across_rolls(self, tmp_path):
        threshold = BronzeWriter.PART_ROW_THRESHOLD
        writer = BronzeWriter(tmp_path, "snap-1")

        writer.write_batch({"charges": _make_df(threshold)})
        writer.write_batch({"charges": _make_df(5)})
        writer.close()

        assert writer._total_rows["charges"] == threshold + 5

    def test_row_count_resets_after_roll(self, tmp_path):
        threshold = BronzeWriter.PART_ROW_THRESHOLD
        writer = BronzeWriter(tmp_path, "snap-1")

        writer.write_batch({"charges": _make_df(threshold)})
        # After the roll, _row_counts should be 0
        assert writer._row_counts["charges"] == 0
        writer.close()


# ---------------------------------------------------------------------------
# Context manager / close
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_files_readable_after_exit(self, tmp_path):
        with BronzeWriter(tmp_path, "snap-1") as writer:
            writer.write_batch({"charges": _make_df(3)})

        part = _part_path(tmp_path, "charges", "snap-1")
        table = pq.read_table(str(part))
        assert table.num_rows == 3

    def test_close_is_idempotent(self, tmp_path):
        writer = BronzeWriter(tmp_path, "snap-1")
        writer.write_batch({"charges": _make_df(1)})
        writer.close()
        writer.close()  # should not raise

    def test_row_counts_include_seen_empty_tables(self, tmp_path):
        writer = BronzeWriter(tmp_path, "snap-1")
        writer.write_batch(
            {"charges": _make_df(2), "optional": pl.DataFrame(schema=_simple_schema())}
        )
        writer.close()

        assert writer.row_counts == {"charges": 2, "optional": 0}
