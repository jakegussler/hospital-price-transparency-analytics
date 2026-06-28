"""Tests for external reference source registry support."""

from __future__ import annotations

import pyarrow as pa
import pytest
import yaml

from hpt.reference.config import ReferenceStorageConfig
from hpt.reference.registry import ReferenceRegistryError, load_reference_sources
from hpt.reference.schema import pyarrow_fields, pyarrow_type


def test_load_reference_sources_from_yaml(tmp_path):
    registry = tmp_path / "sources.yml"
    registry.write_text(
        yaml.safe_dump(
            {
                "sources": {
                    "sample": {
                        "name": "sample_codes",
                        "code_type": "sample",
                        "url": "https://example.test/sample.zip",
                        "member": "sample.txt",
                        "parser": "sample_parser",
                        "code_edition": "2026",
                        "effective_start": "2026-01-01",
                        "effective_end": "2026-12-31",
                        "release_date": "2026-01-01",
                        "extra_fields": [
                            {"name": "weight", "type": "float64"},
                            {"name": "active", "type": "bool"},
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    sources = load_reference_sources(registry)

    assert set(sources) == {"sample"}
    assert sources["sample"].name == "sample_codes"
    assert sources["sample"].field_types == [("weight", "float64"), ("active", "bool")]


def test_load_reference_sources_rejects_missing_sources_mapping(tmp_path):
    registry = tmp_path / "sources.yml"
    registry.write_text(yaml.safe_dump({"not_sources": {}}), encoding="utf-8")

    with pytest.raises(ReferenceRegistryError, match="sources"):
        load_reference_sources(registry)


def test_reference_storage_config_uses_env_roots(tmp_path, monkeypatch):
    reference_root = tmp_path / "reference-bronze"
    raw_root = tmp_path / "reference-raw"
    monkeypatch.setenv("HPT_REFERENCE_ROOT", str(reference_root))
    monkeypatch.setenv("HPT_REFERENCE_RAW_ROOT", str(raw_root))

    cfg = ReferenceStorageConfig.from_env()

    assert cfg.reference_root == reference_root
    assert cfg.raw_root == raw_root


def test_pyarrow_type_mapping_is_centralized():
    assert pyarrow_type("string") == pa.string()
    assert pyarrow_type("float64") == pa.float64()
    assert pyarrow_fields([("flag", "bool")]) == [("flag", pa.bool_())]


def test_pyarrow_type_rejects_unknown_registry_type():
    with pytest.raises(ValueError, match="Unknown reference field type"):
        pyarrow_type("not-a-type")
