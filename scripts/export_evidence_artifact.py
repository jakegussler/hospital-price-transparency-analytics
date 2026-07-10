#!/usr/bin/env python
"""Export allowlisted Gold BI marts for the Evidence.dev app."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from hpt.presentation.evidence_export import (
    DEFAULT_CORPUS_LABEL,
    EvidenceExportError,
    export_evidence_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_build_id() -> str | None:
    """Best-effort short git commit id for public provenance metadata."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    build_id = result.stdout.strip()
    return build_id or None


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
        "--build-id",
        default=None,
        help="Build identifier written to public metadata. Defaults to the git short commit.",
    )
    parser.add_argument(
        "--dictionary-yml",
        type=Path,
        default=REPO_ROOT / "transform" / "models" / "gold" / "bi" / "_gold_bi_models.yml",
        help="dbt schema yml parsed into the public data dictionary artifact.",
    )
    parser.add_argument(
        "--downloads-dir",
        type=Path,
        default=Path("apps/evidence/static/downloads"),
        help="Directory to receive the public download bundle (Parquet + CSV + README).",
    )
    parser.add_argument(
        "--skip-downloads",
        action="store_true",
        help="Skip writing the public download bundle.",
    )
    parser.add_argument(
        "--skip-source-hash",
        action="store_true",
        help="Skip SHA-256 hashing of the source DuckDB file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    build_id = args.build_id if args.build_id is not None else resolve_build_id()
    try:
        row_counts = export_evidence_artifact(
            source_duckdb=args.source_duckdb,
            target_dir=args.target_dir,
            replace=args.replace,
            corpus_label=args.corpus_label,
            compute_source_hash=not args.skip_source_hash,
            build_id=build_id,
            dictionary_yml=args.dictionary_yml,
            downloads_dir=None if args.skip_downloads else args.downloads_dir,
        )
    except EvidenceExportError as exc:
        print(f"error: {exc}")
        return 1

    for table_name, row_count in row_counts.items():
        print(f"{table_name}: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
