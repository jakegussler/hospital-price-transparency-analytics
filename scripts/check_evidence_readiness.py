#!/usr/bin/env python
"""Check whether the Evidence BI artifact is ready for a public demo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from hpt.presentation.evidence_export import (
    DEFAULT_EVIDENCE_READINESS_RULES,
    EvidenceExportError,
    check_evidence_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-duckdb",
        type=Path,
        default=Path(os.getenv("HPT_DUCKDB_PATH", "data/hpt.duckdb")),
        help="DuckDB warehouse to inspect. Defaults to HPT_DUCKDB_PATH or data/hpt.duckdb.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        issues = check_evidence_readiness(
            source_duckdb=args.source_duckdb,
            rules=DEFAULT_EVIDENCE_READINESS_RULES,
        )
    except EvidenceExportError as exc:
        print(f"error: {exc}")
        return 1

    if issues:
        print("error: Evidence readiness checks failed:")
        for issue in issues:
            print(f"- {issue.message}")
        return 1

    print("Evidence readiness checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
