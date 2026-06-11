"""Manifest-aware invariants for snapshot-scoped dbt processing boundaries."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from dbt.cli.main import dbtRunner

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSFORM_DIR = PROJECT_ROOT / "transform"
SNAPSHOT_MODELS_MACRO = TRANSFORM_DIR / "macros" / "incremental_retention.sql"

INTENTIONALLY_UNSCOPED: set[tuple[str, str]] = set()
ACCUMULATED_UNSCOPED_ALLOWLIST: set[tuple[str, str]] = set()


@pytest.fixture(scope="session")
def manifest(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    target_path = tmp_path_factory.mktemp("dbt-target")
    log_path = tmp_path_factory.mktemp("dbt-logs")
    result = dbtRunner().invoke(
        [
            "parse",
            "--project-dir",
            str(TRANSFORM_DIR),
            "--profiles-dir",
            str(TRANSFORM_DIR),
            "--target-path",
            str(target_path),
            "--log-path",
            str(log_path),
            "--no-partial-parse",
        ]
    )
    assert result.success, "dbt parse failed; inspect captured dbt output for details"
    return json.loads((target_path / "manifest.json").read_text())


def _model_nodes(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        unique_id: node
        for unique_id, node in manifest["nodes"].items()
        if node["resource_type"] == "model"
    }


def _snapshot_model_names_from_macro() -> set[str]:
    macro_sql = SNAPSHOT_MODELS_MACRO.read_text()
    macro_body = macro_sql.split("{% macro hpt_snapshot_grained_incremental_models()", 1)[1]
    macro_body = macro_body.split("{%- endmacro %}", 1)[0]
    return set(re.findall(r"'([^']+)'", macro_body))


def _has_scoped_ref(raw_code: str, model_name: str) -> bool:
    return bool(
        re.search(rf"hpt_scoped_ref\(\s*['\"]{re.escape(model_name)}['\"]\s*\)", raw_code)
    )


def _has_scoped_source(raw_code: str, source_name: str, table_name: str) -> bool:
    return bool(
        re.search(
            rf"hpt_scoped_source\(\s*['\"]{re.escape(source_name)}['\"]\s*,\s*"
            rf"['\"]{re.escape(table_name)}['\"]\s*\)",
            raw_code,
        )
    )


def test_snapshot_model_registry_matches_incremental_manifest(manifest: dict[str, object]) -> None:
    manifest_snapshot_models = {
        node["name"]
        for node in _model_nodes(manifest).values()
        if node["config"]["materialized"] == "incremental"
        and node["config"].get("unique_key") == "snapshot_id"
    }

    assert _snapshot_model_names_from_macro() == manifest_snapshot_models


def test_staging_models_are_canonical_unscoped_views(manifest: dict[str, object]) -> None:
    staging_nodes = [
        node
        for node in _model_nodes(manifest).values()
        if node["name"].startswith("stg_bronze__")
    ]

    assert len(staging_nodes) == 15
    for node in staging_nodes:
        assert "hpt_snapshot_filter" not in node["raw_code"], node["name"]
        assert "hpt_scoped_" not in node["raw_code"], node["name"]


def test_bronze_and_staging_inputs_are_scoped_at_consumers(manifest: dict[str, object]) -> None:
    model_nodes = _model_nodes(manifest)
    sources = manifest["sources"]

    for node in model_nodes.values():
        if node["name"].startswith("stg_bronze__"):
            continue

        for dependency_id in node["depends_on"]["nodes"]:
            edge = (node["name"], dependency_id)
            if edge in INTENTIONALLY_UNSCOPED:
                continue

            if dependency_id in sources:
                source = sources[dependency_id]
                if source["source_name"] == "bronze":
                    assert _has_scoped_source(
                        node["raw_code"], source["source_name"], source["name"]
                    ), edge
            elif dependency_id in model_nodes:
                dependency = model_nodes[dependency_id]
                if dependency["name"].startswith("stg_bronze__"):
                    assert _has_scoped_ref(node["raw_code"], dependency["name"]), edge


def test_accumulated_snapshot_inputs_are_scoped(manifest: dict[str, object]) -> None:
    model_nodes = _model_nodes(manifest)
    snapshot_names = _snapshot_model_names_from_macro()
    nodes_by_name = {node["name"]: node for node in model_nodes.values()}
    checked: set[str] = set()

    def assert_scoped_dependencies(node: dict[str, object]) -> None:
        if node["unique_id"] in checked:
            return
        checked.add(node["unique_id"])

        for dependency_id in node["depends_on"]["nodes"]:
            dependency = model_nodes.get(dependency_id)
            if dependency is None:
                continue

            edge = (node["name"], dependency["name"])
            if dependency["name"] in snapshot_names:
                assert edge not in ACCUMULATED_UNSCOPED_ALLOWLIST
                assert _has_scoped_ref(node["raw_code"], dependency["name"]), edge
            elif dependency["config"]["materialized"] == "ephemeral":
                assert_scoped_dependencies(dependency)

    for snapshot_name in snapshot_names:
        assert_scoped_dependencies(nodes_by_name[snapshot_name])

    assert not ACCUMULATED_UNSCOPED_ALLOWLIST


def test_reconciliation_inputs_are_scoped(manifest: dict[str, object]) -> None:
    model_nodes = _model_nodes(manifest)
    snapshot_names = _snapshot_model_names_from_macro()

    reconciliation_nodes = [
        node
        for node in manifest["nodes"].values()
        if node["resource_type"] == "test" and node["name"].startswith("reconcile_")
    ]

    for node in reconciliation_nodes:
        for dependency_id in node["depends_on"]["nodes"]:
            dependency = model_nodes.get(dependency_id)
            if dependency is None:
                continue
            if (
                dependency["name"].startswith("stg_bronze__")
                or dependency["name"] in snapshot_names
            ):
                assert _has_scoped_ref(node["raw_code"], dependency["name"]), (
                    node["name"],
                    dependency["name"],
                )


def test_audit_models_are_unscoped_views_outside_snapshot_registry(
    manifest: dict[str, object],
) -> None:
    snapshot_names = _snapshot_model_names_from_macro()
    audit_nodes = [
        node
        for node in _model_nodes(manifest).values()
        if "audit" in node["config"]["tags"]
    ]

    assert {node["name"] for node in audit_nodes} == {
        "stg_audit__run_events",
        "stg_audit__attempts",
        "audit__runs",
        "audit__attempts",
        "audit__attempt_stages",
        "audit__attempt_row_counts",
    }
    for node in audit_nodes:
        assert node["config"]["materialized"] == "view", node["name"]
        assert node["name"] not in snapshot_names
        assert "hpt_scoped_" not in node["raw_code"], node["name"]
        assert "hpt_snapshot_filter" not in node["raw_code"], node["name"]
