"""Integration tests for the downloader using pytest-httpx and tmp_path fsspec."""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile

import pytest

from hpt.ingest.config import (
    ClientConfig,
    DownloadConfig,
    StorageConfig,
)
from hpt.ingest.download import (
    Outcome,
    _build_client,
    download_all,
    download_hospital,
)
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.registry.models import HospitalSource, MrfSource


@pytest.fixture()
def client_cfg():
    return ClientConfig(
        connect_timeout_s=5,
        read_timeout_s=30,
        retries=0,
        user_agent="hpt-test/0.1",
        timeout_s=60,
    )


@pytest.fixture()
def download_cfg(client_cfg):
    return DownloadConfig(
        storage=StorageConfig(raw_base_uri="file:///unused"),
        client=client_cfg,
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


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestFirstFetch:
    def test_downloads_and_creates_snapshot(
        self, httpx_mock, storage, snapshots, client_cfg, caplog
    ):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(client_cfg)

        with caplog.at_level(logging.DEBUG, logger="hpt.ingest.download"):
            assert logging.getLogger("hpt.ingest.download").isEnabledFor(logging.DEBUG)
            result = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert result.outcome == Outcome.DOWNLOADED
        assert result.file_hash == hashlib.sha256(MRF_BYTES_V1).hexdigest()
        assert result.bytes_transferred == len(MRF_BYTES_V1)
        assert result.snapshot is not None
        assert result.snapshot.valid_from is not None
        assert result.http_status == 200
        assert result.hash_changed is True
        assert result.stage_statuses["request_transfer"] == "success"

    def test_raw_file_exists_on_disk(self, httpx_mock, storage, snapshots, client_cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(client_cfg)
        download_hospital(hospital, storage, snapshots, client)
        client.close()

        files = storage.ls(storage.raw_path("test-hosp", "charges.csv").rsplit("/", 1)[0])
        assert len(files) >= 1

    def test_zip_download_remains_zipped_in_raw(self, httpx_mock, storage, snapshots, client_cfg):
        archive = _zip_bytes({"charges.csv": MRF_BYTES_V1})
        httpx_mock.add_response(
            url="https://example.com/charges.zip",
            content=archive,
            headers={"content-type": "application/zip"},
        )
        hospital = _make_hospital("https://example.com/charges.zip")
        client = _build_client(client_cfg)

        result = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert result.outcome == Outcome.DOWNLOADED
        assert result.final_path is not None
        assert result.final_path.endswith("charges.zip")
        assert storage.exists(result.final_path)
        with storage.open(result.final_path, "rb") as fh:
            assert fh.read() == archive


class TestUnchangedFetch:
    def test_second_identical_fetch_is_unchanged(self, httpx_mock, storage, snapshots, client_cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        hospital = _make_hospital()
        client = _build_client(client_cfg)

        r1 = download_hospital(hospital, storage, snapshots, client)
        r2 = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert r1.outcome == Outcome.DOWNLOADED
        assert r2.outcome == Outcome.UNCHANGED
        assert r2.file_hash == r1.file_hash
        assert r2.snapshot is None
        assert r2.resolved_snapshot_id == r1.snapshot.snapshot_id
        assert r2.resolved_source_file_name == r1.snapshot.source_file_name
        assert r2.hash_changed is False


class TestChangedFetch:
    def test_different_content_writes_new_snapshot(
        self, httpx_mock, storage, snapshots, client_cfg
    ):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V2)
        hospital = _make_hospital()
        client = _build_client(client_cfg)

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
    def test_dry_run_no_download(self, storage, snapshots, client_cfg):
        hospital = _make_hospital()
        client = _build_client(client_cfg)
        result = download_hospital(hospital, storage, snapshots, client, dry_run=True)
        client.close()

        assert result.outcome == Outcome.DRY_RUN
        assert result.bytes_transferred == 0
        assert snapshots.current_hash("test-hosp") is None


class TestFailure:
    def test_http_error_returns_failed(self, httpx_mock, storage, snapshots, client_cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", status_code=500)
        hospital = _make_hospital()
        client = _build_client(client_cfg)

        result = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert result.outcome == Outcome.FAILED
        assert result.error is not None
        assert snapshots.current_hash("test-hosp") is None

    def test_failure_does_not_corrupt_existing(self, httpx_mock, storage, snapshots, client_cfg):
        httpx_mock.add_response(url="https://example.com/charges.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/charges.csv", status_code=503)
        hospital = _make_hospital()
        client = _build_client(client_cfg)

        r1 = download_hospital(hospital, storage, snapshots, client)
        r2 = download_hospital(hospital, storage, snapshots, client)
        client.close()

        assert r1.outcome == Outcome.DOWNLOADED
        assert r2.outcome == Outcome.FAILED
        assert snapshots.current_hash("test-hosp") == r1.file_hash


class TestDownloadAll:
    def test_iterates_registry(self, httpx_mock, storage, snapshots, download_cfg):
        httpx_mock.add_response(url="https://example.com/a.csv", content=MRF_BYTES_V1)
        httpx_mock.add_response(url="https://example.com/b.csv", content=MRF_BYTES_V2)

        hospitals = [
            _make_hospital("https://example.com/a.csv", hospital_id="h-a"),
            _make_hospital("https://example.com/b.csv", hospital_id="h-b"),
        ]
        results = download_all(hospitals, storage, snapshots, download_cfg)

        assert len(results) == 2
        assert all(r.outcome == Outcome.DOWNLOADED for r in results)

    def test_one_failure_does_not_abort(self, httpx_mock, storage, snapshots, download_cfg):
        httpx_mock.add_response(url="https://example.com/a.csv", status_code=500)
        httpx_mock.add_response(url="https://example.com/b.csv", content=MRF_BYTES_V1)

        hospitals = [
            _make_hospital("https://example.com/a.csv", hospital_id="h-a"),
            _make_hospital("https://example.com/b.csv", hospital_id="h-b"),
        ]
        results = download_all(hospitals, storage, snapshots, download_cfg)

        outcomes = {r.hospital_id: r.outcome for r in results}
        assert outcomes["h-a"] == Outcome.FAILED
        assert outcomes["h-b"] == Outcome.DOWNLOADED
