"""Tests for the hospital source registry loader and models."""

from __future__ import annotations

from pathlib import Path

import pytest

from hpt.registry.loader import RegistryError, get_hospital, load_registry
from hpt.registry.models import HospitalSource

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadRegistry:
    def test_valid_registry(self):
        hospitals = load_registry(FIXTURES / "valid_registry.yml")
        assert len(hospitals) == 2
        assert all(isinstance(h, HospitalSource) for h in hospitals)
        assert hospitals[0].hospital_id == "test-hospital-a"
        assert hospitals[1].hospital_id == "test-hospital-b"

    def test_valid_fields(self):
        hospitals = load_registry(FIXTURES / "valid_registry.yml")
        a = hospitals[0]
        assert a.canonical_hospital_name == "Test Hospital A"
        assert a.canonical_state == "FL"
        assert a.hospital_type == "community"
        assert a.health_system == "Test System"
        assert str(a.mrf_source.url) == "https://example.com/hospital-a/standardcharges.csv"
        assert a.mrf_source.expected_format == "csv_wide"
        assert a.mrf_source.notes is None

    def test_nullable_health_system(self):
        hospitals = load_registry(FIXTURES / "valid_registry.yml")
        b = hospitals[1]
        assert b.health_system is None
        assert b.mrf_source.notes == "Large JSON file"

    def test_duplicate_ids_raises(self):
        with pytest.raises(RegistryError, match="Duplicate hospital_id"):
            load_registry(FIXTURES / "duplicate_ids.yml")

    def test_bad_enum_raises(self):
        with pytest.raises(RegistryError, match="bad-enum-hospital"):
            load_registry(FIXTURES / "bad_enum.yml")

    def test_ndjson_expected_format_rejected(self, tmp_path):
        p = tmp_path / "ndjson.yml"
        p.write_text(
            "hospitals:\n"
            "  - hospital_id: ndjson-hospital\n"
            "    canonical_hospital_name: X\n"
            "    canonical_state: FL\n"
            "    hospital_type: community\n"
            "    mrf_source:\n"
            "      url: https://example.com/x.ndjson\n"
            "      expected_format: ndjson\n"
        )
        with pytest.raises(RegistryError, match="ndjson-hospital"):
            load_registry(p)

    def test_bad_url_raises(self):
        with pytest.raises(RegistryError, match="bad-url-hospital"):
            load_registry(FIXTURES / "bad_url.yml")

    def test_missing_field_raises(self):
        with pytest.raises(RegistryError, match="missing-field"):
            load_registry(FIXTURES / "missing_field.yml")

    def test_missing_file_raises(self):
        with pytest.raises(RegistryError, match="Registry file not found"):
            load_registry(FIXTURES / "nonexistent.yml")

    def test_empty_yaml_raises(self, tmp_path):
        p = tmp_path / "empty.yml"
        p.write_text("---\nfoo: bar\n")
        with pytest.raises(RegistryError, match="top-level 'hospitals' key"):
            load_registry(p)


class TestGetHospital:
    def test_found(self):
        h = get_hospital("test-hospital-a", FIXTURES / "valid_registry.yml")
        assert h.hospital_id == "test-hospital-a"

    def test_not_found(self):
        with pytest.raises(KeyError, match="no-such-id"):
            get_hospital("no-such-id", FIXTURES / "valid_registry.yml")


class TestActivation:
    _REGISTRY = (
        "hospitals:\n"
        "  - hospital_id: active-hospital\n"
        "    canonical_hospital_name: Active\n"
        "    canonical_state: TN\n"
        "    hospital_type: community\n"
        "    mrf_source:\n"
        "      url: https://example.com/active.csv\n"
        "      expected_format: csv_wide\n"
        "  - hospital_id: inactive-hospital\n"
        "    canonical_hospital_name: Inactive\n"
        "    canonical_state: CA\n"
        "    hospital_type: community\n"
        "    active: false\n"
        "    mrf_source:\n"
        "      url: https://example.com/inactive.csv\n"
        "      expected_format: csv_wide\n"
    )

    def _write(self, tmp_path: Path) -> Path:
        p = tmp_path / "activation.yml"
        p.write_text(self._REGISTRY)
        return p

    def test_active_defaults_true(self, tmp_path):
        hospitals = load_registry(self._write(tmp_path), include_inactive=True)
        by_id = {h.hospital_id: h for h in hospitals}
        assert by_id["active-hospital"].active is True
        assert by_id["inactive-hospital"].active is False

    def test_default_excludes_inactive(self, tmp_path):
        hospitals = load_registry(self._write(tmp_path))
        assert [h.hospital_id for h in hospitals] == ["active-hospital"]

    def test_include_inactive_returns_all(self, tmp_path):
        hospitals = load_registry(self._write(tmp_path), include_inactive=True)
        assert {h.hospital_id for h in hospitals} == {
            "active-hospital",
            "inactive-hospital",
        }

    def test_get_hospital_finds_inactive(self, tmp_path):
        h = get_hospital("inactive-hospital", self._write(tmp_path))
        assert h.hospital_id == "inactive-hospital"

    def test_duplicate_check_spans_inactive(self, tmp_path):
        p = tmp_path / "dupe.yml"
        p.write_text(
            self._REGISTRY + "  - hospital_id: active-hospital\n"
            "    canonical_hospital_name: Dupe\n"
            "    canonical_state: TN\n"
            "    hospital_type: community\n"
            "    active: false\n"
            "    mrf_source:\n"
            "      url: https://example.com/dupe.csv\n"
            "      expected_format: csv_wide\n"
        )
        with pytest.raises(RegistryError, match="Duplicate hospital_id"):
            load_registry(p)


class TestHospitalIdValidation:
    def test_expanded_state_registry_loads(self):
        # States span the full registry (active + inactive); deactivating the
        # non-Nashville corpus must not drop these CMS state codes from the file.
        hospitals = load_registry(include_inactive=True)
        states = {h.canonical_state for h in hospitals}

        assert {"CA", "GA", "ID", "IL", "MI", "MN", "WI"}.issubset(states)

    def test_registry_accepts_cms_state_codes_outside_current_seed(self, tmp_path):
        p = tmp_path / "valid_territory.yml"
        p.write_text(
            "hospitals:\n"
            "  - hospital_id: territory-hospital\n"
            "    canonical_hospital_name: X\n"
            "    canonical_state: PR\n"
            "    hospital_type: community\n"
            "    mrf_source:\n"
            "      url: https://example.com/x.csv\n"
            "      expected_format: csv_wide\n"
        )

        hospitals = load_registry(p)

        assert hospitals[0].canonical_state == "PR"

    def test_empty_id_rejected(self, tmp_path):
        p = tmp_path / "bad_id.yml"
        p.write_text(
            "hospitals:\n"
            "  - hospital_id: ''\n"
            "    canonical_hospital_name: X\n"
            "    canonical_state: FL\n"
            "    hospital_type: community\n"
            "    mrf_source:\n"
            "      url: https://example.com/x.csv\n"
            "      expected_format: csv_wide\n"
        )
        with pytest.raises(RegistryError):
            load_registry(p)

    def test_slug_with_special_chars_rejected(self, tmp_path):
        p = tmp_path / "special.yml"
        p.write_text(
            "hospitals:\n"
            "  - hospital_id: 'bad hospital!'\n"
            "    canonical_hospital_name: X\n"
            "    canonical_state: FL\n"
            "    hospital_type: community\n"
            "    mrf_source:\n"
            "      url: https://example.com/x.csv\n"
            "      expected_format: csv_wide\n"
        )
        with pytest.raises(RegistryError):
            load_registry(p)
