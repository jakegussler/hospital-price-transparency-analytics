#!/usr/bin/env python3

"""Run the MRF sniffer across files under data/raw and print results."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import fsspec

# Ensure src/ is importable when running this script directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hpt.ingest.mrf_sniffer import Layout, sniff_schema

SUPPORTED_EXTENSIONS = (".csv", ".json", ".csv.gz", ".json.gz")


@dataclass(frozen=True)
class SniffResult:
    path: Path
    ok: bool
    layout: str | None
    version: str | None
    error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively scan data/raw for CSV/JSON files and run the MRF sniffer "
            "on each one."
        )
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=REPO_ROOT / "data" / "raw",
        help="Root directory to scan recursively (default: data/raw).",
    )
    return parser.parse_args()


def is_supported_mrf(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith(SUPPORTED_EXTENSIONS)


def iter_candidate_files(data_root: Path) -> list[Path]:
    if not data_root.exists():
        return []

    files = [p for p in data_root.rglob("*") if p.is_file() and is_supported_mrf(p)]
    files.sort()
    return files


def run_sniffer(path: Path, fs: fsspec.AbstractFileSystem) -> SniffResult:
    try:
        info = sniff_schema(str(path), fs)
    except Exception as exc:
        return SniffResult(
            path=path, ok=False, layout=None, version=None, error=f"{type(exc).__name__}: {exc}"
        )

    return SniffResult(
        path=path,
        ok=info.layout != Layout.UNKNOWN,
        layout=info.layout.value,
        version=info.version,
        error=None,
    )


def print_results(results: list[SniffResult], data_root: Path) -> None:
    print(f"Scanned root: {data_root}")
    print(f"Candidate files found: {len(results)}")
    print("")

    for result in results:
        rel_path = result.path.relative_to(REPO_ROOT)
        if result.error:
            print(f"[ERROR] {rel_path} :: {result.error}")
            continue

        status = "OK" if result.ok else "UNKNOWN"
        print(
            f"[{status}] {rel_path} :: layout={result.layout}, "
            f"version={result.version or 'None'}"
        )

    ok_count = sum(1 for r in results if r.ok)
    unknown_count = sum(1 for r in results if (not r.ok) and (r.error is None))
    error_count = sum(1 for r in results if r.error is not None)

    print("")
    print(
        "Summary: "
        f"ok={ok_count}, unknown={unknown_count}, errors={error_count}, total={len(results)}"
    )


def main() -> int:
    args = parse_args()
    data_root = args.data_root.resolve()
    candidates = iter_candidate_files(data_root)

    if not data_root.exists():
        print(f"Data root does not exist: {data_root}")
        return 1

    if not candidates:
        print(f"No CSV/JSON files found under: {data_root}")
        return 1

    fs = fsspec.filesystem("local")
    results = [run_sniffer(path, fs) for path in candidates]
    print_results(results, data_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
