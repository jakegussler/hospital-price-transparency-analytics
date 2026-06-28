"""Configuration for external reference-data storage roots."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from hpt.utils.paths import get_default_data_root


def get_default_reference_root() -> Path:
    """Return the default Bronze Parquet root for external reference data."""
    return get_default_data_root() / "reference" / "bronze"


def get_default_reference_raw_root() -> Path:
    """Return the default raw-download root for external reference data."""
    return get_default_data_root() / "reference" / "raw"


@dataclass(frozen=True)
class ReferenceStorageConfig:
    """Storage roots used by reference-data loaders."""

    reference_root: Path = field(default_factory=get_default_reference_root)
    raw_root: Path = field(default_factory=get_default_reference_raw_root)

    @classmethod
    def from_env(
        cls,
        *,
        reference_root: Path | None = None,
        raw_root: Path | None = None,
    ) -> ReferenceStorageConfig:
        return cls(
            reference_root=reference_root
            or Path(os.environ.get("HPT_REFERENCE_ROOT", get_default_reference_root())),
            raw_root=raw_root
            or Path(os.environ.get("HPT_REFERENCE_RAW_ROOT", get_default_reference_raw_root())),
        )
