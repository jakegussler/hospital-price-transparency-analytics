"""Tests for exporting registry metadata to dbt seed CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from hpt.cli import export_hospitals_seed_logic
from hpt.registry.seed_export import HOSPITALS_SEED_COLUMNS, write_hospitals_seed

FIXTURES = Path(__file__).parent / "fixtures"


def test_write_hospitals_seed_uses_registry_shape(tmp_path):
    output_path = tmp_path / "hospitals.csv"

    written_path = write_hospitals_seed(
        registry_path=FIXTURES / "valid_registry.yml",
        output_path=output_path,
    )

    assert written_path == output_path
    with output_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert rows[0] == {
        "hospital_id": "test-hospital-a",
        "canonical_hospital_name": "Test Hospital A",
        "canonical_state": "FL",
        "hospital_type": "community",
        "health_system": "Test System",
        "mrf_url": "https://example.com/hospital-a/standardcharges.csv",
        "expected_format": "csv_wide",
    }
    assert rows[1]["health_system"] == ""


def test_write_hospitals_seed_uses_env_registry_path(monkeypatch, tmp_path):
    output_path = tmp_path / "hospitals.csv"
    monkeypatch.setenv("HPT_REGISTRY_PATH", str(FIXTURES / "valid_registry.yml"))

    write_hospitals_seed(output_path=output_path)

    with output_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == HOSPITALS_SEED_COLUMNS
        rows = list(reader)

    assert [row["hospital_id"] for row in rows] == ["test-hospital-a", "test-hospital-b"]


def test_export_hospitals_seed_logic_returns_error_for_bad_registry(tmp_path):
    exit_code = export_hospitals_seed_logic(
        registry_path=FIXTURES / "missing_field.yml",
        output_path=tmp_path / "hospitals.csv",
    )

    assert exit_code == 2


def test_committed_hospitals_seed_matches_active_bundled_registry(tmp_path):
    generated_path = tmp_path / "hospitals.csv"

    write_hospitals_seed(output_path=generated_path)

    committed_path = Path(__file__).parents[1] / "transform" / "seeds" / "hospitals.csv"
    assert generated_path.read_text(encoding="utf-8") == committed_path.read_text(
        encoding="utf-8"
    )
