#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_JSON_PATH = Path(
    "data/352528741_vanderbilt-university-medical-center_standardcharges.json"
)


def truncate_text(value: str, max_len: int = 80) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def scalar_summary(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"bool ({value})"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"int ({value})"
    if isinstance(value, float):
        return f"float ({value})"
    if isinstance(value, str):
        return f"str len={len(value)} sample={truncate_text(value)!r}"
    return type(value).__name__


def describe(
    value: Any,
    indent: int = 0,
    max_list_samples: int = 3,
    max_depth: int = 10,
) -> None:
    prefix = "  " * indent
    if indent >= max_depth:
        print(f"{prefix}... max depth reached")
        return

    if isinstance(value, dict):
        print(f"{prefix}object with {len(value)} keys")
        for key, child in value.items():
            child_type = type(child).__name__
            print(f"{prefix}  - {key!r}: {child_type}")
            if isinstance(child, (dict, list)):
                describe(
                    child,
                    indent=indent + 2,
                    max_list_samples=max_list_samples,
                    max_depth=max_depth,
                )
            else:
                print(f"{prefix}      {scalar_summary(child)}")
        return

    if isinstance(value, list):
        print(f"{prefix}array with {len(value)} items")
        if not value:
            return
        sample_count = min(len(value), max_list_samples)
        for i in range(sample_count):
            item = value[i]
            item_type = type(item).__name__
            print(f"{prefix}  [{i}] {item_type}")
            if isinstance(item, (dict, list)):
                describe(
                    item,
                    indent=indent + 2,
                    max_list_samples=max_list_samples,
                    max_depth=max_depth,
                )
            else:
                print(f"{prefix}      {scalar_summary(item)}")
        remaining = len(value) - sample_count
        if remaining > 0:
            print(f"{prefix}  ... {remaining} more items not shown")
        return

    print(f"{prefix}{scalar_summary(value)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and print the structure of a JSON file."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"Path to JSON file (default: {DEFAULT_JSON_PATH}).",
    )
    parser.add_argument(
        "--max-list-samples",
        type=int,
        default=3,
        help="How many items to sample per list (default: 3).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        help="Maximum recursion depth to print (default: 10).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_list_samples < 1:
        raise ValueError("--max-list-samples must be >= 1")
    if args.max_depth < 1:
        raise ValueError("--max-depth must be >= 1")

    try:
        with args.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        print(f"Error loading JSON file {args.path}: {exc}")
        return 1

    print(f"Loaded JSON from: {args.path}")
    print(f"Top-level type: {type(data).__name__}")
    describe(
        data,
        indent=0,
        max_list_samples=args.max_list_samples,
        max_depth=args.max_depth,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())