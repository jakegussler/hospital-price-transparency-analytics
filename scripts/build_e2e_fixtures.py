"""Build deterministic offline fixtures for the ingest-to-dbt e2e test."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from hpt.ingest.snapshot import SnapshotRecord

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "e2e"

CSV_V3_ATTESTATION = (
    "To the best of its knowledge and belief, this hospital has included all "
    "applicable standard charge information in accordance with the requirements "
    "of 45 CFR 180.50, and the information encoded is true, accurate, and "
    "complete as of the date in the file. This hospital has included all "
    "payer-specific negotiated charges in dollars that can be expressed as a "
    "dollar amount. For payer-specific negotiated charges that cannot be "
    "expressed as a dollar amount in the machine-readable file or not knowable "
    "in advance, the hospital attests that the payer-specific negotiated charge "
    "is based on a contractual algorithm, percentage or formula that precludes "
    "the provision of a dollar amount and has provided all necessary information "
    "available to the hospital for the public to be able to derive the dollar "
    "amount, including, but not limited to, the specific fee schedule or "
    "components referenced in such percentage, algorithm or formula."
)


@dataclass(frozen=True)
class FixtureHospital:
    hospital_id: str
    canonical_hospital_name: str
    canonical_state: str
    hospital_type: str
    health_system: str | None
    expected_format: str
    source_url: str
    source_file_name: str
    snapshot_id: str
    ingested_at: datetime

    @property
    def raw_relative_path(self) -> Path:
        date = self.ingested_at.strftime("%Y-%m-%d")
        return (
            Path("raw")
            / f"hospital_id={self.hospital_id}"
            / f"ingested_at={date}"
            / self.source_file_name
        )


FIXTURE_HOSPITALS: tuple[FixtureHospital, ...] = (
    FixtureHospital(
        hospital_id="lincoln-health-system",
        canonical_hospital_name="Lincoln Health System",
        canonical_state="TN",
        hospital_type="community",
        health_system="Lincoln Health System",
        expected_format="csv_wide",
        source_url=(
            "https://hhlincolnhealth.org/wp-content/uploads/"
            "882472117_hh-health-system-lincoln-inc_standardcharges.csv"
        ),
        source_file_name="lincoln_standardcharges.csv",
        snapshot_id="cd725773-f575-45dd-a796-adf9c9805a14",
        ingested_at=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
    ),
    FixtureHospital(
        hospital_id="ballad-sycamore",
        canonical_hospital_name="Sycamore Shoals Hospital",
        canonical_state="TN",
        hospital_type="community",
        health_system="Ballad Health",
        expected_format="csv_tall",
        source_url=(
            "https://www.balladhealth.org/sites/default/files/2026-03/"
            "620476282_sycamore-shoals-hospital_standardcharges.zip"
        ),
        source_file_name="ballad_sycamore_standardcharges.csv",
        snapshot_id="209991a1-5cfa-42b8-a2bf-9e40595898db",
        ingested_at=datetime(2026, 1, 3, 12, 0, tzinfo=UTC),
    ),
    FixtureHospital(
        hospital_id="ngmc-gainesville",
        canonical_hospital_name="Northeast Georgia Medical Center Gainesville",
        canonical_state="GA",
        hospital_type="community",
        health_system="Northeast Georgia Health System",
        expected_format="json",
        source_url=(
            "https://www.nghs.com/wp-content/uploads/581713478_"
            "northeast-georgia-medical-center-gainesville_standardcharges.json"
        ),
        source_file_name="ngmc_gainesville_standardcharges.json",
        snapshot_id="97e28644-a4fc-4b3c-9c5c-8e9cf650500e",
        ingested_at=datetime(2026, 1, 4, 12, 0, tzinfo=UTC),
    ),
)

FIXTURE_HOSPITAL_IDS = tuple(h.hospital_id for h in FIXTURE_HOSPITALS)
FIXTURE_SNAPSHOT_IDS = tuple(h.snapshot_id for h in FIXTURE_HOSPITALS)


def main() -> None:
    _reset_fixture_root()
    _write_registry()
    for hospital in FIXTURE_HOSPITALS:
        raw_bytes = _raw_bytes_for(hospital)
        raw_path = FIXTURE_ROOT / hospital.raw_relative_path
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_bytes)
        _write_snapshot_metadata(hospital, hashlib.sha256(raw_bytes).hexdigest())


def _reset_fixture_root() -> None:
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    FIXTURE_ROOT.mkdir(parents=True)


def _write_registry() -> None:
    lines = ["hospitals:"]
    for hospital in FIXTURE_HOSPITALS:
        health_system = "null" if hospital.health_system is None else hospital.health_system
        lines.extend(
            [
                f"  - hospital_id: {hospital.hospital_id}",
                f"    canonical_hospital_name: {hospital.canonical_hospital_name}",
                f"    canonical_state: {hospital.canonical_state}",
                f"    hospital_type: {hospital.hospital_type}",
                f"    health_system: {health_system}",
                "    mrf_source:",
                f"      url: {hospital.source_url}",
                f"      expected_format: {hospital.expected_format}",
                "",
            ]
        )
    (FIXTURE_ROOT / "registry.yml").write_text("\n".join(lines), encoding="utf-8")


def _raw_bytes_for(hospital: FixtureHospital) -> bytes:
    if hospital.expected_format == "csv_wide":
        return _csv_bytes(_wide_rows(hospital))
    if hospital.expected_format == "csv_tall":
        return _csv_bytes(_tall_rows(hospital))
    if hospital.expected_format == "json":
        payload = _json_payload(hospital)
        return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    raise ValueError(f"Unsupported fixture format: {hospital.expected_format}")


def _csv_bytes(rows: list[list[str]]) -> bytes:
    from io import StringIO

    handle = StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def _header_rows(hospital: FixtureHospital, state: str, license_number: str) -> list[list[str]]:
    return [
        [
            "hospital_name",
            "last_updated_on",
            "version",
            "location_name",
            "hospital_address",
            f"license_number|{state}",
            "type_2_npi",
            CSV_V3_ATTESTATION,
            "attester_name",
        ],
        [
            hospital.canonical_hospital_name,
            "2026-01-01",
            "3.0.0",
            "Main Campus",
            "100 Main St",
            license_number,
            "1234567890",
            "true",
            "Jane Smith",
        ],
    ]


def _wide_rows(hospital: FixtureHospital) -> list[list[str]]:
    return [
        *_header_rows(hospital, "TN", "TN12345"),
        [
            "description",
            "code|1",
            "code|1|type",
            "setting",
            "billing_class",
            "standard_charge|gross",
            "standard_charge|discounted_cash",
            "standard_charge|min",
            "standard_charge|max",
            "standard_charge|Aetna|PPO|negotiated_dollar",
            "standard_charge|Aetna|PPO|methodology",
            "standard_charge|Cigna|HMO|negotiated_dollar",
            "standard_charge|Cigna|HMO|methodology",
        ],
        [
            "Emergency room visit",
            "99283",
            "CPT",
            "outpatient",
            "facility",
            "500",
            "250",
            "175",
            "180",
            "175",
            "fee schedule",
            "180",
            "fee schedule",
        ],
        [
            "Chest X-Ray",
            "71046",
            "CPT",
            "outpatient",
            "facility",
            "220",
            "110",
            "90",
            "90",
            "90",
            "fee schedule",
            "",
            "",
        ],
    ]


def _tall_rows(hospital: FixtureHospital) -> list[list[str]]:
    return [
        *_header_rows(hospital, "TN", "TN67890"),
        [
            "description",
            "code|1",
            "code|1|type",
            "setting",
            "billing_class",
            "standard_charge|gross",
            "standard_charge|discounted_cash",
            "standard_charge|min",
            "standard_charge|max",
            "standard_charge|negotiated_dollar",
            "standard_charge|methodology",
            "payer_name",
            "plan_name",
            "count",
        ],
        [
            "Basic metabolic panel",
            "80048",
            "CPT",
            "outpatient",
            "facility",
            "120",
            "80",
            "60",
            "60",
            "60",
            "fee schedule",
            "Aetna",
            "PPO",
            "0",
        ],
        [
            "Observation room",
            "0760",
            "RC",
            "outpatient",
            "facility",
            "900",
            "450",
            "300",
            "300",
            "300",
            "fee schedule",
            "Cigna",
            "HMO",
            "0",
        ],
    ]


def _json_payload(hospital: FixtureHospital) -> dict[str, Any]:
    return {
        "hospital_name": hospital.canonical_hospital_name,
        "last_updated_on": "2026-01-01",
        "version": "3.0.0",
        "license_information": {"state": "GA", "license_number": "GA24680"},
        "attestation": {
            "attestation": CSV_V3_ATTESTATION,
            "confirm_attestation": True,
            "attester_name": "Jane Smith",
        },
        "location_name": ["Main Campus"],
        "hospital_address": ["200 Main St"],
        "type_2_npi": ["1234567890"],
        "standard_charge_information": [
            {
                "description": "MRI lumbar spine",
                "code_information": [{"code": "72148", "type": "CPT"}],
                "standard_charges": [
                    {
                        "setting": "outpatient",
                        "billing_class": "facility",
                        "gross_charge": 1200.0,
                        "discounted_cash": 600.0,
                        "payers_information": [
                            {
                                "payer_name": "Aetna",
                                "plan_name": "PPO",
                                "methodology": "fee schedule",
                                "standard_charge_dollar": 500.0,
                            }
                        ],
                        "minimum": 500.0,
                        "maximum": 600.0,
                    }
                ],
            },
            {
                "description": "Physical therapy visit",
                "code_information": [{"code": "97110", "type": "CPT"}],
                "standard_charges": [
                    {
                        "setting": "outpatient",
                        "billing_class": "professional",
                        "gross_charge": 180.0,
                        "discounted_cash": 90.0,
                        "payers_information": [
                            {
                                "payer_name": "Cigna",
                                "plan_name": "HMO",
                                "methodology": "fee schedule",
                                "standard_charge_dollar": 75.0,
                            }
                        ],
                        "minimum": 75.0,
                        "maximum": 90.0,
                    }
                ],
            },
        ],
    }


def _write_snapshot_metadata(hospital: FixtureHospital, file_hash: str) -> None:
    record = SnapshotRecord(
        snapshot_id=hospital.snapshot_id,
        hospital_id=hospital.hospital_id,
        source_url=hospital.source_url,
        source_file_name=hospital.source_file_name,
        file_hash=file_hash,
        ingested_at=hospital.ingested_at,
        valid_from=hospital.ingested_at,
    )
    path = (
        FIXTURE_ROOT
        / "metadata"
        / "hospital_mrf_snapshots"
        / f"hospital_id={hospital.hospital_id}"
        / f"{hospital.snapshot_id}.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(record.to_table(), path)


if __name__ == "__main__":
    main()
