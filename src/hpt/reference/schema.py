"""Schema helpers for external reference-data registries."""

from __future__ import annotations

import pyarrow as pa

_PYARROW_TYPES = {
    "bool": pa.bool_,
    "boolean": pa.bool_,
    "date32": pa.date32,
    "float": pa.float64,
    "float64": pa.float64,
    "int": pa.int64,
    "int64": pa.int64,
    "string": pa.string,
    "timestamp_us_utc": lambda: pa.timestamp("us", tz="UTC"),
}


def pyarrow_type(type_name: str) -> pa.DataType:
    """Resolve a registry type name to a PyArrow data type."""
    try:
        factory = _PYARROW_TYPES[type_name.lower()]
    except KeyError as exc:
        valid = ", ".join(sorted(_PYARROW_TYPES))
        raise ValueError(
            f"Unknown reference field type {type_name!r}; expected one of: {valid}"
        ) from exc
    return factory()


def pyarrow_fields(fields: list[tuple[str, str]]) -> list[tuple[str, pa.DataType]]:
    """Resolve registry field definitions into PyArrow schema tuples."""
    return [(name, pyarrow_type(type_name)) for name, type_name in fields]
