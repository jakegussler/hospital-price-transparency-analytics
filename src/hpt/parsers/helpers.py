"""Shared parser utility helpers."""

from __future__ import annotations

from typing import Any

import polars as pl


def _df(
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType],
) -> pl.DataFrame:
    """Build a Polars DataFrame with a fixed schema, handling empty row sets."""
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema)


def _iso(value: Any) -> str | None:
    """Render datetime-ish values as ISO-8601 strings; pass through strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
