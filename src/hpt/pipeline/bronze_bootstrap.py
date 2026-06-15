"""Ensure every declared dbt Bronze source has a schema-only Parquet sentinel."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from hpt.parsers.schemas import BRONZE_BOOTSTRAP_SCHEMAS

logger = logging.getLogger(__name__)

BOOTSTRAP_SNAPSHOT_ID = "__bootstrap__"
BOOTSTRAP_FILE_NAME = "_schema.parquet"


@dataclass(frozen=True)
class BronzeBootstrapResult:
    """Tables whose schema sentinels were created, updated, or unchanged."""

    created: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]


def ensure_bronze_source_bootstrap(
    bronze_root: Path,
    source_definition_path: Path,
    *,
    log: logging.Logger | None = None,
) -> BronzeBootstrapResult:
    """Create or repair zero-row Parquet sentinels for every dbt Bronze source."""
    log = log or logger
    bronze_root = Path(bronze_root)
    declared_tables = _load_declared_bronze_tables(Path(source_definition_path))
    _validate_schema_registry(declared_tables)
    _require_real_snapshot_metadata(bronze_root)

    created: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []

    for table_name in declared_tables:
        expected_schema = _arrow_schema(BRONZE_BOOTSTRAP_SCHEMAS[table_name])
        sentinel = (
            bronze_root
            / table_name
            / f"snapshot_id={BOOTSTRAP_SNAPSHOT_ID}"
            / BOOTSTRAP_FILE_NAME
        )
        if _has_expected_schema(sentinel, expected_schema):
            unchanged.append(table_name)
            continue

        existed = sentinel.exists()
        _write_empty_parquet_atomically(sentinel, expected_schema)
        (updated if existed else created).append(table_name)

    result = BronzeBootstrapResult(
        created=tuple(created),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
    )
    log.info(
        "bronze_source_bootstrap_complete",
        extra={
            "bronze_root": str(bronze_root),
            "created_count": len(result.created),
            "updated_count": len(result.updated),
            "unchanged_count": len(result.unchanged),
            "created_tables": list(result.created),
            "updated_tables": list(result.updated),
        },
    )
    return result


def _load_declared_bronze_tables(source_definition_path: Path) -> list[str]:
    try:
        definition = yaml.safe_load(source_definition_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f"Unable to read Bronze source definitions from {source_definition_path}: {exc}"
        ) from exc

    if not isinstance(definition, dict) or not isinstance(definition.get("sources"), list):
        raise ValueError(
            f"Malformed Bronze source definitions in {source_definition_path}."
        )
    if not all(isinstance(source, dict) for source in definition["sources"]):
        raise ValueError(
            f"Malformed Bronze source definitions in {source_definition_path}."
        )

    bronze_sources = [
        source for source in definition["sources"] if source.get("name") == "bronze"
    ]
    if len(bronze_sources) != 1:
        raise ValueError(
            f"Expected exactly one 'bronze' source in {source_definition_path}, "
            f"found {len(bronze_sources)}."
        )

    tables = bronze_sources[0].get("tables")
    if not isinstance(tables, list) or not all(
        isinstance(table, dict)
        and isinstance(table.get("name"), str)
        and table["name"].strip()
        for table in tables
    ):
        raise ValueError(
            f"Malformed Bronze table declarations in {source_definition_path}."
        )

    table_names = [table["name"].strip() for table in tables]
    duplicates = sorted({name for name in table_names if table_names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Duplicate declared Bronze source tables: {', '.join(duplicates)}.")
    return table_names


def _validate_schema_registry(declared_tables: list[str]) -> None:
    declared = set(declared_tables)
    registered = set(BRONZE_BOOTSTRAP_SCHEMAS)
    missing = sorted(declared - registered)
    extra = sorted(registered - declared)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing schemas: {', '.join(missing)}")
        if extra:
            details.append(f"undeclared schemas: {', '.join(extra)}")
        raise ValueError(f"Bronze source/schema registry mismatch ({'; '.join(details)}).")


def _require_real_snapshot_metadata(bronze_root: Path) -> None:
    metadata_root = bronze_root / "hospital_mrf_snapshots"
    has_real_metadata = any(
        f"snapshot_id={BOOTSTRAP_SNAPSHOT_ID}" not in path.parts
        for path in metadata_root.rglob("*.parquet")
    )
    if not has_real_metadata:
        raise FileNotFoundError(
            "No non-bootstrap hospital_mrf_snapshots Parquet files were found under "
            f"{metadata_root}. Ingest at least one snapshot before running dbt."
        )


def _arrow_schema(schema: dict[str, pl.DataType]) -> pa.Schema:
    return pl.DataFrame(schema=schema).to_arrow().schema


def _has_expected_schema(path: Path, expected_schema: pa.Schema) -> bool:
    if not path.exists():
        return False
    try:
        return pq.read_schema(path).equals(expected_schema)
    except (OSError, pa.ArrowException):
        return False


def _write_empty_parquet_atomically(path: Path, schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        pq.write_table(schema.empty_table(), temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
