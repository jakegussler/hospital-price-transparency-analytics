"""Export registry-backed dbt seed files."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from hpt.registry.loader import load_registry
from hpt.registry.models import HospitalSource
from hpt.utils.paths import get_project_root

HOSPITALS_SEED_COLUMNS = [
    "hospital_id",
    "canonical_hospital_name",
    "canonical_state",
    "hospital_type",
    "health_system",
    "mrf_url",
    "expected_format",
]


def get_default_hospitals_seed_path(project_root: Path | None = None) -> Path:
    """Return the canonical dbt hospitals seed path."""
    return (project_root or get_project_root()).resolve() / "transform" / "seeds" / "hospitals.csv"


def registry_path_from_env(path: Path | None = None) -> Path | None:
    """Resolve an explicit registry path or the HPT_REGISTRY_PATH override."""
    if path is not None:
        return path
    env_path = os.environ.get("HPT_REGISTRY_PATH")
    return Path(env_path) if env_path else None


def hospital_seed_row(hospital: HospitalSource) -> dict[str, str]:
    """Convert a registry hospital entry into the dbt hospitals seed shape."""
    return {
        "hospital_id": hospital.hospital_id,
        "canonical_hospital_name": hospital.canonical_hospital_name,
        "canonical_state": hospital.canonical_state,
        "hospital_type": hospital.hospital_type,
        "health_system": hospital.health_system or "",
        "mrf_url": str(hospital.mrf_source.url),
        "expected_format": hospital.mrf_source.expected_format,
    }


def write_hospitals_seed(
    *,
    registry_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Write the dbt hospitals seed from the active registry and return its path."""
    resolved_registry_path = registry_path_from_env(registry_path)
    hospitals = load_registry(resolved_registry_path) if resolved_registry_path else load_registry()
    resolved_output_path = output_path or get_default_hospitals_seed_path()
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

    with resolved_output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=HOSPITALS_SEED_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(hospital_seed_row(hospital) for hospital in hospitals)

    return resolved_output_path
