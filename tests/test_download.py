"""Integration tests for the downloader using pytest-httpx and tmp_path fsspec."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from hpt.ingest.config import IngestConfig
from hpt.ingest.download import (
    Outcome,
    download_all,
    download_hospital,
    _build_client,
)
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.registry.models import HospitalSource, MrfSource


@pytest.fixture()
def cfg():
    return IngestConfig(
        bronze_base_uri="file:///unused",
        http_connect_timeout=5,
        http_read_timeout=30,
        http_retries=0,
        user_agent="hpt-test/0.1",
        http_timeout=60,
    )


@pytest.fixture()
def storage(tmp_path):
    return BronzeStorage(f"file://{tmp_path}")


@pytest.fixture()
def snapshots(storage):
    return SnapshotManager(storage)


def _make_hospital(url: str = "https://example.com/charges.csv", **overrides) -> HospitalSource:
    defaults = dict(
        hospital_id="test-hosp",
        canonical_hospital_name="Test Hospital",
        canonical_state="FL",
        hospital_type="community",
        mrf_source=MrfSource(url=url, expected_format="csv_wide"),
    )
    defaults.update(overrides)
    return HospitalSource(**defaults)


MRF_BYTES_V1 = b"code,description,price\nCPT001,Test,100.00\n"
MRF_BYTES_V2 = b"code,description,price\nCPT001,Test,200.00\nCPT002,Other,300.00\n"


class TestFirstFetch:
    def test_downloads_and_creates_snapshot(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(cfg)

        result = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert result.outcome == Outcome.DOWNLOADED
        assert result.file_hash == hashlib.sha256(MRF_BYTES_V1).hexdigest()
        assert result.bytes_transferred == len(MRF_BYTES_V1)
        assert result.snapshot is not None
        assert result.snapshot.is_current_snapshot is True

    def test_raw_file_exists_on_disk(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(cfg)
        download_hospital(hospital, storage, snapshots, client)
        client.close()

        files = storage.ls(storage.raw_path("test-hosp", "charges.csv").rsplit("/", 1)[0])
        assert len(files) >= 1


class TestUnchangedFetch:
    def test_second_identical_fetch_is_unchanged(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(cfg)

        r1 = download_hospital(hospital, storage, snapshots, client)
        r2 = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert r1.outcome == Outcome.DOWNLOADED
        assert r2.outcome == Outcome.UNCHANGED
        assert r2.file_hash == r1.file_hash
        assert r2.snapshot is None


class TestChangedFetch:
    def test_different_content_writes_new_snapshot(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V2)
        hospital = _make_hospital()
        client = _build_client(cfg)

        r1 = download_hospital(hospital, storage, snapshots, client)
        r2 = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert r1.outcome == Outcome.DOWNLOADED
        assert r2.outcome == Outcome.DOWNLOADED
        assert r1.file_hash != r2.file_hash

        current = snapshots.get_current_snapshot("test-hosp")
        assert current is not None
        assert current.file_hash == r2.file_hash


class TestDryRun:
    def test_dry_run_no_download(self, storage, snapshots, cfg):
        hospital = _make_hospital()
        client = _build_client(cfg)
        result = download_hospital(hospital, storage, snapshots, client, dry_run=True)
        client.close()

        assert result.outcome == Outcome.DRY_RUN
        assert result.bytes_transferred == 0
        assert snapshots.current_hash("test-hosp") is None


class TestFailure:
    def test_http_error_returns_failed(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", status_code=500)
        hospital = _make_hospital()
        client = _build_client(cfg)

        result = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert result.outcome == Outcome.FAILED
        assert result.error is not None
        assert snapshots.current_hash("test-hosp") is None

    def test_failure_does_not_corrupt_existing(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", status_code=503)
        hospital = _make_hospital()
        client = _build_client(cfg)

        r1 = download_hospital(hospital, storage, snapshots, client)
        r2 = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert r1.outcome == Outcome.DOWNLOADED
        assert r2.outcome == Outcome.FAILED
        assert snapshots.current_hash("test-hosp") == r1.file_hash


class TestDownloadAll:
    def test_iterates_registry(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/a.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/b.csv", content=MRF_BYTES_V2)

        hospitals = [
            _make_hospital("https://example.com/a.csv", hospital_id="h-a"),
            _make_hospital("https://example.com/b.csv", hospital_id="h-b"),
        ]
        results = download_all(hospitals, storage, snapshots, cfg)

        assert len(results) == 2
        assert all(r.outcome == Outcome.DOWNLOADED for r in results)

    def test_one_failure_does_not_abort(self, httpx_mock, storage, snapshots, cfg):
        httpx_mock.add_response(url="https://example.com/a.csv", status_code=500)
        httpx_mock.add_response(url="https://example.com/b.csv", content=MRF_BYTES_V1)

        hospitals = [
            _make_hospital("https://example.com/a.csv", hospital_id="h-a"),
            _make_hospital("https://example.com/b.csv", hospital_id="h-b"),
        ]
        results = download_all(hospitals, storage, snapshots, cfg)

        outcomes = {r.hospital_id: r.outcome for r in results}
        assert outcomes["h-a"] == Outcome.FAILED
        assert outcomes["h-b"] == Outcome.DOWNLOADED
