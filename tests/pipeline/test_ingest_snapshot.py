"""Tests for hpt.pipeline.ingest_snapshot."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

from hpt.ingest.mrf_sniffer import Layout
from hpt.ingest.snapshot import SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.parsers.csv_tall import CsvTallParser
from hpt.parsers.csv_wide import CsvWideParser
from hpt.parsers.json_mrf import JsonMrfParser
from hpt.pipeline.ingest_snapshot import (
    _build_parser,
    _snapshot_meta,
    ingest_snapshot,
    resolve_local_path,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_INGESTED_AT = datetime(2025, 6, 15, tzinfo=UTC)
_DATE_STR = "2025-06-15"


def _make_snapshot(
    hospital_id: str = "h1",
    source_file_name: str = "charges.json",
    file_hash: str = "abcdef123456789012",
    ingested_at: datetime = _INGESTED_AT,
) -> SnapshotRecord:
    return SnapshotRecord(
        snapshot_id="snap-001",
        hospital_id=hospital_id,
        source_url="https://example.com/charges.json",
        source_file_name=source_file_name,
        file_hash=file_hash,
        ingested_at=ingested_at,
        valid_from=ingested_at,
    )


def _partition_dir(tmp_path: Path, hospital_id: str = "h1") -> Path:
    return tmp_path / "raw" / f"hospital_id={hospital_id}" / f"ingested_at={_DATE_STR}"


def _place_file(tmp_path: Path, filename: str, hospital_id: str = "h1") -> Path:
    d = _partition_dir(tmp_path, hospital_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    p.write_bytes(b"{}")
    return p


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    path.write_bytes(buf.getvalue())


def _minimal_mrf_json() -> dict[str, Any]:
    return {
        "hospital_name": "Test Hospital",
        "last_updated_on": "2025-01-01",
        "version": "3.0.0",
        "license_information": {"state": "FL"},
        "attestation": {
            "attestation": "I attest",
            "confirm_attestation": True,
            "attester_name": "Jane",
        },
        "location_name": ["Main"],
        "hospital_address": ["123 Main St"],
        "type_2_npi": [],
        "modifier_information": [],
        "standard_charge_information": [
            {
                "description": "X-Ray",
                "code_information": [{"code": "CPT001", "type": "CPT"}],
                "standard_charges": [
                    {
                        "setting": "outpatient",
                        "gross_charge": 200.0,
                        "payers_information": [
                            {
                                "payer_name": "Aetna",
                                "plan_name": "PPO",
                                "methodology": "fee schedule",
                                "standard_charge_dollar": 150.0,
                            }
                        ],
                        "minimum": 100.0,
                        "maximum": 300.0,
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# resolve_local_path
# ---------------------------------------------------------------------------


class TestResolveLocalPath:
    def test_exact_filename_match(self, tmp_path):
        _place_file(tmp_path, "charges.json")
        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot(source_file_name="charges.json")

        result = resolve_local_path(snap, storage)

        assert result.name == "charges.json"

    def test_hash_suffix_match(self, tmp_path):
        file_hash = "abcdef123456789012"
        _place_file(tmp_path, f"charges__{file_hash[:12]}.json")
        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot(source_file_name="charges.json", file_hash=file_hash)

        result = resolve_local_path(snap, storage)

        assert file_hash[:12] in result.name

    def test_stem_match(self, tmp_path):
        # Decompression stripped the .gz suffix, leaving charges.json
        _place_file(tmp_path, "charges.json")
        storage = BronzeStorage(f"file://{tmp_path}")
        # source_file_name was originally charges.json.gz
        snap = _make_snapshot(source_file_name="charges.json.gz")

        result = resolve_local_path(snap, storage)

        assert "charges" in result.name

    def test_single_file_fallback(self, tmp_path):
        _place_file(tmp_path, "unrelated_name.json")
        storage = BronzeStorage(f"file://{tmp_path}")
        # No exact match, no hash match, no stem match, but only 1 file → fallback
        snap = _make_snapshot(source_file_name="original.json", file_hash="000000000000")

        result = resolve_local_path(snap, storage)

        assert result.name == "unrelated_name.json"

    def test_empty_partition_raises(self, tmp_path):
        # Create the directory but leave it empty
        _partition_dir(tmp_path).mkdir(parents=True)
        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot()

        with pytest.raises(FileNotFoundError, match="No files found"):
            resolve_local_path(snap, storage)

    def test_no_candidate_raises(self, tmp_path):
        # Multiple files, none match
        _place_file(tmp_path, "alpha.json")
        _place_file(tmp_path, "beta.json")
        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot(source_file_name="original.json", file_hash="000000000000")

        with pytest.raises(FileNotFoundError, match="Could not identify"):
            resolve_local_path(snap, storage)


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def _kwargs(self, tmp_path: Path) -> dict:
        return dict(
            hospital_config={"hospital_id": "h1"},
            snapshot_meta={"snapshot_id": "s1", "hospital_id": "h1"},
            quarantine_root=tmp_path / "quarantine",
        )

    def test_json_returns_json_mrf_parser(self, tmp_path):
        parser = _build_parser(Layout.JSON, **self._kwargs(tmp_path))
        assert isinstance(parser, JsonMrfParser)

    def test_csv_tall_returns_csv_tall_parser(self, tmp_path):
        parser = _build_parser(Layout.CSV_TALL, **self._kwargs(tmp_path))
        assert isinstance(parser, CsvTallParser)

    def test_csv_wide_returns_csv_wide_parser(self, tmp_path):
        parser = _build_parser(Layout.CSV_WIDE, **self._kwargs(tmp_path))
        assert isinstance(parser, CsvWideParser)


# ---------------------------------------------------------------------------
# _snapshot_meta
# ---------------------------------------------------------------------------


class TestSnapshotMeta:
    def test_projection(self):
        snap = _make_snapshot()
        meta = _snapshot_meta(snap, source_format="json", schema_version="3.0.0")

        assert meta["snapshot_id"] == snap.snapshot_id
        assert meta["hospital_id"] == snap.hospital_id
        assert meta["source_url"] == snap.source_url
        assert meta["source_file_name"] == snap.source_file_name
        assert meta["source_format"] == "json"
        assert meta["file_hash"] == snap.file_hash
        assert meta["ingested_at"] == snap.ingested_at
        assert meta["valid_from"] == snap.valid_from
        assert meta["schema_version"] == "3.0.0"

    def test_schema_version_none_when_not_detected(self):
        snap = _make_snapshot()
        meta = _snapshot_meta(snap, source_format="json", schema_version=None)
        assert meta["schema_version"] is None


# ---------------------------------------------------------------------------
# ingest_snapshot — end-to-end
# ---------------------------------------------------------------------------


class TestIngestSnapshotE2E:
    def test_writes_bronze_parquet(self, tmp_path):
        # Write a minimal JSON MRF to the expected partition
        mrf_data = json.dumps(_minimal_mrf_json()).encode()
        partition = _partition_dir(tmp_path)
        partition.mkdir(parents=True, exist_ok=True)
        mrf_file = partition / "charges.json"
        mrf_file.write_bytes(mrf_data)

        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot(source_file_name="charges.json")
        bronze_root = tmp_path / "bronze"
        quarantine_root = tmp_path / "quarantine"

        result = ingest_snapshot(
            snapshot=snap,
            hospital_config={"hospital_id": "h1"},
            storage=storage,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
        )

        assert result["snapshot_id"] == "snap-001"
        assert result["source_format"] == "json"

        # Bronze output should contain at minimum hospital_mrf_snapshots
        snap_parts = list(
            (bronze_root / "hospital_mrf_snapshots").rglob("*.parquet")
        )
        assert len(snap_parts) >= 1

    def test_ingests_zip_without_expanding_raw(self, tmp_path):
        mrf_data = json.dumps(_minimal_mrf_json()).encode()
        partition = _partition_dir(tmp_path)
        partition.mkdir(parents=True, exist_ok=True)
        raw_zip = partition / "charges.zip"
        _write_zip(raw_zip, {"nested/charges.json": mrf_data})

        storage = BronzeStorage(f"file://{tmp_path}")
        snap = _make_snapshot(source_file_name="charges.zip")
        bronze_root = tmp_path / "bronze"
        quarantine_root = tmp_path / "quarantine"

        result = ingest_snapshot(
            snapshot=snap,
            hospital_config={"hospital_id": "h1"},
            storage=storage,
            bronze_root=bronze_root,
            quarantine_root=quarantine_root,
        )

        assert result["snapshot_id"] == "snap-001"
        assert result["source_format"] == "json"
        assert result["local_path"].endswith("charges.zip")
        assert result["parser_path"].endswith(".json")
        assert raw_zip.exists()
        assert not (partition / "charges.json").exists()
        tmp_files = list((tmp_path / ".tmp").glob("*")) if (tmp_path / ".tmp").exists() else []
        assert tmp_files == []
