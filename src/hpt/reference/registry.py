"""Registry loading for external reference-data sources."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_DEFAULT_REGISTRY = Path(__file__).resolve().parent / "sources.yml"


class ReferenceRegistryError(Exception):
    """Raised when the reference source registry is missing or invalid."""


class ReferenceField(BaseModel):
    """One source-specific output field defined by the registry."""

    name: str
    type: str


class ReferenceSource(BaseModel):
    """Spec for one external reference release."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(default="")
    name: str
    code_type: str
    url: str
    member: str
    parser: str
    code_edition: str
    effective_start: dt.date
    effective_end: dt.date
    release_date: str
    source: str = "CMS"
    license: str = "public-domain"
    extra_fields: list[ReferenceField] = Field(default_factory=list)

    @field_validator("release_date", mode="before")
    @classmethod
    def normalize_release_date(cls, value: object) -> str:
        if isinstance(value, dt.date):
            return value.isoformat()
        return str(value)

    @property
    def field_types(self) -> list[tuple[str, str]]:
        """Return source-specific output fields as registry type names."""
        return [(field.name, field.type) for field in self.extra_fields]


def load_reference_sources(path: Path = _DEFAULT_REGISTRY) -> dict[str, ReferenceSource]:
    """Read and validate the external reference source registry."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReferenceRegistryError(f"Reference registry file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ReferenceRegistryError(
            f"Reference registry at {path} is invalid YAML: {exc}"
        ) from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("sources"), dict):
        raise ReferenceRegistryError(
            f"Reference registry at {path} must contain a 'sources' mapping"
        )

    sources: dict[str, ReferenceSource] = {}
    for key, entry in raw["sources"].items():
        if not isinstance(entry, dict):
            raise ReferenceRegistryError(f"Reference source {key!r} must be a mapping")
        try:
            source = ReferenceSource.model_validate({"key": key, **entry})
        except ValidationError as exc:
            raise ReferenceRegistryError(
                f"Validation failed for reference source {key!r}:\n{exc}"
            ) from exc
        if key in sources:
            raise ReferenceRegistryError(f"Duplicate reference source key: {key!r}")
        sources[key] = source

    return sources
