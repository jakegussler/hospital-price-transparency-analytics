"""Populate transform/seeds/hospitals.csv from the active hospital registry."""

from __future__ import annotations

import argparse
from pathlib import Path

from hpt.registry.seed_export import write_hospitals_seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=None,
        help="Registry YAML path. Defaults to HPT_REGISTRY_PATH or the bundled registry.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="CSV path to write. Defaults to transform/seeds/hospitals.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    written_path = write_hospitals_seed(
        registry_path=args.registry_path,
        output_path=args.output_path,
    )
    print(f"Wrote hospitals seed: {written_path}")


if __name__ == "__main__":
    main()
