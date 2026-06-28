"""Pydantic models for the hospital source registry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, HttpUrl, field_validator

StateCode = Literal[
    "AL",
    "AK",
    "AS",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FM",
    "FL",
    "GA",
    "GU",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MH",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "MP",
    "OH",
    "OK",
    "OR",
    "PW",
    "PA",
    "PR",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VI",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
]


class MrfSource(BaseModel):
    """Location and format metadata for a hospital's MRF file."""

    url: HttpUrl
    expected_format: Literal["json", "csv_tall", "csv_wide"]
    notes: str | None = None


class HospitalSource(BaseModel):
    """A single hospital entry in the source registry."""

    hospital_id: str
    canonical_hospital_name: str
    canonical_state: StateCode
    hospital_type: Literal[
        "academic_medical_center",
        "community",
        "for_profit",
        "nonprofit",
    ]
    health_system: str | None = None
    active: bool = True
    """Whether this hospital is in the working pipeline set.

    Inactive entries are retained in the registry (URL research is preserved)
    but excluded from bulk download/ingest, the dbt hospitals seed, and the
    all-hospitals dbt resolution. They can still be targeted explicitly by id.
    """
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
