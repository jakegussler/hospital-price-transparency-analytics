"""Tests for runtime configuration models."""

from __future__ import annotations

from pathlib import Path

import pytest

from hpt.ingest.config import (
    ClientConfig,
    DownloadConfig,
    IngestConfig,
    StorageConfig,
)
from hpt.utils.paths import get_default_data_root


class TestTargetValidation:
    def test_single_hospital_target(self):
        cfg = DownloadConfig(hospital_id="  vumc  ")
        assert cfg.hospital_id == "vumc"
        assert cfg.run_all is False

    def test_all_target(self):
        cfg = IngestConfig(run_all=True)
        assert cfg.hospital_id is None
        assert cfg.run_all is True

    def test_missing_target_rejected(self):
        with pytest.raises(ValueError, match="Provide --hospital-id"):
            DownloadConfig()

    def test_ambiguous_target_rejected(self):
        with pytest.raises(ValueError, match="only one"):
            IngestConfig(hospital_id="vumc", run_all=True)


class TestClientConfig:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("HPT_HTTP_CONNECT_TIMEOUT", "1.5")
        monkeypatch.setenv("HPT_HTTP_READ_TIMEOUT", "30.5")
        monkeypatch.setenv("HPT_HTTP_RETRIES", "0")
        monkeypatch.setenv("HPT_USER_AGENT", "hpt-test/1.0")
        monkeypatch.setenv("HPT_HTTP_TIMEOUT", "45")

        cfg = ClientConfig.from_env()

        assert cfg.connect_timeout_s == 1.5
        assert cfg.read_timeout_s == 30.5
        assert cfg.retries == 0
        assert cfg.user_agent == "hpt-test/1.0"
        assert cfg.timeout_s == 45


class TestStorageConfig:
    def test_default_raw_uri_is_stable_across_working_directories(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HPT_RAW_STORAGE_BASE_URI", raising=False)
        monkeypatch.chdir(tmp_path)

        cfg = StorageConfig.from_env()

        assert cfg.raw_base_uri == get_default_data_root().as_uri()

    def test_from_env_defaults_use_canonical_project_data_root(self, monkeypatch):
        monkeypatch.delenv("HPT_RAW_STORAGE_BASE_URI", raising=False)
        monkeypatch.delenv("HPT_PARSED_BRONZE_ROOT", raising=False)
        monkeypatch.delenv("HPT_QUARANTINE_ROOT", raising=False)

        cfg = StorageConfig.from_env()
        data_root = get_default_data_root()

        assert cfg.raw_base_uri == data_root.as_uri()
        assert cfg.bronze_root == data_root / "bronze"
        assert cfg.quarantine_root == data_root / "quarantine"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("HPT_RAW_STORAGE_BASE_URI", "file:///raw")
        monkeypatch.setenv("HPT_PARSED_BRONZE_ROOT", "env/bronze")
        monkeypatch.setenv("HPT_QUARANTINE_ROOT", "env/quarantine")

        cfg = StorageConfig.from_env()

        assert cfg.raw_base_uri == "file:///raw"
        assert cfg.bronze_root == Path("env/bronze")
        assert cfg.quarantine_root == Path("env/quarantine")

    def test_cli_output_values_override_env(self, monkeypatch):
        monkeypatch.setenv("HPT_PARSED_BRONZE_ROOT", "env/bronze")
        monkeypatch.setenv("HPT_QUARANTINE_ROOT", "env/quarantine")

        cfg = StorageConfig.from_env(
            bronze_root=Path("cli/bronze"),
            quarantine_root=Path("cli/quarantine"),
        )

        assert cfg.bronze_root == Path("cli/bronze")
        assert cfg.quarantine_root == Path("cli/quarantine")

    def test_explicit_raw_base_uri_override_wins(self, monkeypatch):
        monkeypatch.setenv("HPT_RAW_STORAGE_BASE_URI", "file:///from-env")

        cfg = StorageConfig.from_env(raw_base_uri=Path("data/custom-raw"))

        assert cfg.raw_base_uri == Path("data/custom-raw").resolve().as_uri()


class TestPhaseConfigs:
    def test_download_config_from_env(self, monkeypatch):
        monkeypatch.setenv("HPT_RAW_STORAGE_BASE_URI", "file:///raw")
        monkeypatch.setenv("HPT_REGISTRY_PATH", "registry/test.yml")

        cfg = DownloadConfig.from_env(run_all=True, dry_run=True, force=True)

        assert cfg.storage.raw_base_uri == "file:///raw"
        assert cfg.registry_path == Path("registry/test.yml")
        assert cfg.dry_run is True
        assert cfg.force is True

    def test_ingest_config_from_env_with_overrides(self):
        cfg = IngestConfig.from_env(
            hospital_id="vumc",
            bronze_root=Path("data/test-bronze"),
            quarantine_root=Path("data/test-quarantine"),
            registry_path=Path("registry/test.yml"),
        )

        assert cfg.hospital_id == "vumc"
        assert cfg.registry_path == Path("registry/test.yml")
        assert cfg.storage.bronze_root == Path("data/test-bronze")
        assert cfg.storage.quarantine_root == Path("data/test-quarantine")
