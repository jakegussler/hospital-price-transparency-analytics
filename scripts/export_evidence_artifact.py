#!/usr/bin/env python
"""Export allowlisted Gold BI marts for the Evidence.dev app."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from hpt.presentation.evidence_export import (
    DEFAULT_CORPUS_LABEL,
    EvidenceExportError,
    export_evidence_artifact,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-duckdb",
        type=Path,
        default=Path(os.getenv("HPT_DUCKDB_PATH", "data/hpt.duckdb")),
        help="DuckDB warehouse to read. Defaults to HPT_DUCKDB_PATH or data/hpt.duckdb.",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path("apps/evidence/sources/hpt/data"),
        help="Directory to receive generated public Parquet artifacts.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Atomically replace an existing generated target directory.",
    )
    parser.add_argument(
        "--corpus-label",
        default=DEFAULT_CORPUS_LABEL,
        help="Public corpus label written to metadata.",
    )
    parser.add_argument(
        "--skip-source-hash",
        action="store_true",
        help="Skip SHA-256 hashing of the source DuckDB file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        row_counts = export_evidence_artifact(
            source_duckdb=args.source_duckdb,
            target_dir=args.target_dir,
            replace=args.replace,
            corpus_label=args.corpus_label,
            compute_source_hash=not args.skip_source_hash,
        )
    except EvidenceExportError as exc:
        print(f"error: {exc}")
        return 1

    for table_name, row_count in row_counts.items():
        print(f"{table_name}: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

