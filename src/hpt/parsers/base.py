"""Abstract base parser that all format-specific parsers implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    import polars as pl


class BaseParser(ABC):
    """Contract for format-specific MRF parsers.

    Each concrete parser (JSON, CSV tall, CSV wide) implements ``parse()``
    which yields batches keyed by Bronze table name. All formats share the
    ``hospital_mrf_snapshots``, ``hospital_locations``, and ``type2_npi``
    tables; JSON parsers additionally populate the 7 JSON-only tables.

    Parameters
    ----------
    hospital_config:
        Registry entry for the hospital whose file is being parsed. Must
        contain at least ``hospital_id``.
    snapshot_meta:
        Pipeline-generated snapshot fields produced by
        :class:`hpt.ingest.snapshot.SnapshotManager`. Expected keys:
        ``snapshot_id``, ``source_url``, ``source_file_name``, ``file_hash``,
        ``ingested_at``, ``valid_from``. The parser merges these with
        source-derived header fields to produce the ``hospital_mrf_snapshots``
        row. Snapshot currentness is derived downstream by dbt, not stored here.
    quarantine_root:
        Directory where records that fail Pydantic validation are written
        as JSONL for later inspection. One subdirectory per ``snapshot_id``.
    """

    def __init__(
        self,
        hospital_config: dict[str, Any],
        snapshot_meta: dict[str, Any],
        quarantine_root: Path,
    ) -> None:
        self.hospital_config = hospital_config
        self.hospital_id: str = hospital_config["hospital_id"]
        self.snapshot_meta = snapshot_meta
        self.quarantine_root = quarantine_root

    @property
    def quarantine_counts(self) -> dict[str, int]:
        """Return categorized structural quarantine counts for this parse."""
        return {}

    @abstractmethod
    def parse(self, file_path: Path) -> Iterator[dict[str, "pl.DataFrame"]]:
        """Yield batches of Bronze rows as ``{table_name: DataFrame}``.

        The first yielded batch MUST contain the ``hospital_mrf_snapshots``,
        ``hospital_locations``, and ``type2_npi`` rows so that downstream
        consumers can anchor subsequent batches by ``snapshot_id``.

        Subsequent batches contain charge / modifier data. Empty DataFrames
        may be included and are expected to be skipped by the writer.
        """
