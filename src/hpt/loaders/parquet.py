"""Write parser output as Bronze Parquet files.

Each table is written under a Hive-partitioned directory
``{bronze_root}/{table}/snapshot_id={id}/part-NNN.parquet``. DuckDB reads
these directly with ``read_parquet('bronze/**/*.parquet', hive_partitioning=true)``
and exposes ``snapshot_id`` as a virtual column.

The writer uses :class:`pyarrow.parquet.ParquetWriter` to append batches to
the same file without buffering the full file in memory. A new part file
is opened when :data:`BronzeWriter.PART_ROW_THRESHOLD` rows have been
written to the current part.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from hpt.logging.log_helpers import log_bronze_part_roll

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)


class BronzeWriter:
    """Stream DataFrame batches to snapshot-partitioned Parquet."""

    PART_ROW_THRESHOLD: int = 500_000
    """Open a new part file after this many rows have been written."""

    def __init__(self, bronze_root: Path, snapshot_id: str) -> None:
        self.bronze_root = Path(bronze_root)
        self.snapshot_id = snapshot_id
        self._writers: dict[str, pq.ParquetWriter] = {}
        self._row_counts: dict[str, int] = defaultdict(int)
        self._part_index: dict[str, int] = defaultdict(int)
        self._total_rows: dict[str, int] = defaultdict(int)

    def write_batch(self, batch: dict[str, pl.DataFrame]) -> None:
        """Append each non-empty DataFrame in *batch* to its Parquet file."""
        batch_row_counts: dict[str, int] = {}
        for table_name, df in batch.items():
            if df.is_empty():
                continue
            arrow_table = df.to_arrow()
            writer = self._get_writer(table_name, arrow_table.schema)
            writer.write_table(arrow_table)

            rows = arrow_table.num_rows
            batch_row_counts[table_name] = rows
            self._row_counts[table_name] += rows
            self._total_rows[table_name] += rows
            logger.debug(
                "bronze_batch_write",
                extra={
                    "snapshot_id": self.snapshot_id,
                    "table_name": table_name,
                    "rows": rows,
                    "part_index": self._part_index[table_name],
                    "part_row_count": self._row_counts[table_name],
                },
            )

            if self._row_counts[table_name] >= self.PART_ROW_THRESHOLD:
                self._roll_part(table_name)

        if batch_row_counts:
            logger.info(
                "bronze_batch_written",
                extra={
                    "snapshot_id": self.snapshot_id,
                    "table_count": len(batch_row_counts),
                    "batch_row_counts": batch_row_counts,
                },
            )

    def close(self) -> None:
        """Close every open writer and log per-table row totals."""
        for writer in self._writers.values():
            writer.close()
        self._writers.clear()

        if self._total_rows:
            logger.info(
                "bronze_write_summary",
                extra={
                    "snapshot_id": self.snapshot_id,
                    "row_counts": dict(self._total_rows),
                },
            )

    def __enter__(self) -> "BronzeWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_writer(
        self, table_name: str, schema: pa.Schema
    ) -> pq.ParquetWriter:
        if table_name not in self._writers:
            part_dir = (
                self.bronze_root
                / table_name
                / f"snapshot_id={self.snapshot_id}"
            )
            part_dir.mkdir(parents=True, exist_ok=True)
            part_num = self._part_index[table_name]
            path = part_dir / f"part-{part_num:03d}.parquet"
            self._writers[table_name] = pq.ParquetWriter(str(path), schema)
            logger.info(
                "bronze_table_start",
                extra={
                    "snapshot_id": self.snapshot_id,
                    "table_name": table_name,
                    "part_index": part_num,
                    "path": str(path),
                },
            )
        return self._writers[table_name]

    def _roll_part(self, table_name: str) -> None:
        """Close the current part and bump the part index for the next write."""
        writer = self._writers.pop(table_name, None)
        if writer is not None:
            writer.close()
        self._part_index[table_name] += 1
        log_bronze_part_roll(
            logger,
            snapshot_id=self.snapshot_id,
            table_name=table_name,
            part_index=self._part_index[table_name],
            row_threshold=self.PART_ROW_THRESHOLD,
        )
        self._row_counts[table_name] = 0
