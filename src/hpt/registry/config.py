"""Load and validate the hospital manifest (hospitals.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "manifest" / "hospitals.yaml"


def load_manifest(path: Path = _DEFAULT_MANIFEST) -> list[dict[str, Any]]:
    """Return the list of hospital config dicts from *path*."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("hospitals", [])


def get_hospital(hospital_id: str, path: Path = _DEFAULT_MANIFEST) -> dict[str, Any]:
    """Return a single hospital config by *hospital_id*, or raise."""
    for h in load_manifest(path):
        if h["hospital_id"] == hospital_id:
            return h
    raise KeyError(f"Hospital not found in manifest: {hospital_id}")
