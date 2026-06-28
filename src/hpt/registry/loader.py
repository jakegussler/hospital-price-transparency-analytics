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


def load_registry(
    path: Path = _DEFAULT_REGISTRY, *, include_inactive: bool = False
) -> list[HospitalSource]:
    """Read *path*, validate every entry, and return a list of HospitalSource.

    By default only ``active`` hospitals are returned: this is the working
    pipeline set used by bulk download/ingest, the all-hospitals dbt resolution,
    and the dbt hospitals seed export. Pass ``include_inactive=True`` to return
    the full registry (validation and duplicate-id checks always span every
    entry regardless of activation).
    """
    logger.debug("registry_load_start", extra={"path": str(path)})
    try:
        with open(path) as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise RegistryError(f"Registry file not found: {path}") from exc

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
            raise RegistryError(f"Validation failed for hospital {hid!r}:\n{exc}") from exc

        if hospital.hospital_id in seen_ids:
            raise RegistryError(f"Duplicate hospital_id: {hospital.hospital_id!r}")
        seen_ids.add(hospital.hospital_id)
        hospitals.append(hospital)

    if not include_inactive:
        hospitals = [hospital for hospital in hospitals if hospital.active]

    log_registry_loaded(logger, path=path, n_hospitals=len(hospitals))
    return hospitals


def get_hospital(hospital_id: str, path: Path = _DEFAULT_REGISTRY) -> HospitalSource:
    """Return a single HospitalSource by *hospital_id*, or raise KeyError.

    Explicit lookups span inactive hospitals too, so a deactivated hospital can
    still be targeted by id.
    """
    for h in load_registry(path, include_inactive=True):
        if h.hospital_id == hospital_id:
            return h
    raise KeyError(f"Hospital not found in registry: {hospital_id!r}")


def get_hospitals(hospital_ids: list[str], path: Path = _DEFAULT_REGISTRY) -> list[HospitalSource]:
    """Return a list of HospitalSource by *hospital_ids*, or raise KeyError.

    Explicit lookups span inactive hospitals too, so deactivated hospitals can
    still be targeted by id.
    """
    hospitals_by_id = {h.hospital_id: h for h in load_registry(path, include_inactive=True)}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for hospital_id in hospital_ids:
        if hospital_id not in seen:
            ordered_ids.append(hospital_id)
            seen.add(hospital_id)

    missing = [hospital_id for hospital_id in ordered_ids if hospital_id not in hospitals_by_id]
    if missing:
        raise KeyError(f"Hospitals not found in registry: {missing!r}")

    return [hospitals_by_id[hospital_id] for hospital_id in ordered_ids]
