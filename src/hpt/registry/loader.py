"""Load and validate the hospital source registry (hospitals.yml)."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from hpt.logging.log_helpers import log_registry_loaded
from hpt.registry.models import HospitalSource

_DEFAULT_REGISTRY = Path(__file__).resolve().parent / "hospitals.yml"
logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Raised when the registry file is invalid or inconsistent."""


def load_registry(path: Path = _DEFAULT_REGISTRY) -> list[HospitalSource]:
    """Read *path*, validate every entry, and return a list of HospitalSource."""
    logger.debug("registry_load_start", extra={"path": str(path)})
    with open(path) as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or "hospitals" not in raw:
        raise RegistryError(f"Registry at {path} must contain a top-level 'hospitals' key")

    entries: list[dict] = raw["hospitals"]
    hospitals: list[HospitalSource] = []
    seen_ids: set[str] = set()

    for idx, entry in enumerate(entries):
        hid = entry.get("hospital_id", f"<entry #{idx}>")
        try:
            hospital = HospitalSource.model_validate(entry)
        except ValidationError as exc:
            raise RegistryError(
                f"Validation failed for hospital {hid!r}:\n{exc}"
            ) from exc

        if hospital.hospital_id in seen_ids:
            raise RegistryError(f"Duplicate hospital_id: {hospital.hospital_id!r}")
        seen_ids.add(hospital.hospital_id)
        hospitals.append(hospital)

    log_registry_loaded(logger, path=path, n_hospitals=len(hospitals))
    return hospitals


def get_hospital(
    hospital_id: str, path: Path = _DEFAULT_REGISTRY
) -> HospitalSource:
    """Return a single HospitalSource by *hospital_id*, or raise KeyError."""
    for h in load_registry(path):
        if h.hospital_id == hospital_id:
            return h
    raise KeyError(f"Hospital not found in registry: {hospital_id!r}")
