"""Pydantic models for the hospital source registry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, HttpUrl, field_validator


class MrfSource(BaseModel):
    """Location and format metadata for a hospital's MRF file."""

    url: HttpUrl
    expected_format: Literal["json", "csv_tall", "csv_wide"]
    notes: str | None = None


class HospitalSource(BaseModel):
    """A single hospital entry in the source registry."""

    hospital_id: str
    canonical_hospital_name: str
    canonical_state: Literal["CA", "FL", "GA", "ID", "IL", "MI", "MN", "NC", "TN", "WI"]
    hospital_type: Literal[
        "academic_medical_center",
        "community",
        "for_profit",
        "nonprofit",
    ]
    health_system: str | None = None
    mrf_source: MrfSource

    @field_validator("hospital_id")
    @classmethod
    def _slug_format(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"hospital_id must be a non-empty alphanumeric slug "
                f"(hyphens/underscores allowed), got {v!r}"
            )
        return v
