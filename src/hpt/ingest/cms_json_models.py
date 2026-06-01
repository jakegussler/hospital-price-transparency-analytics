"""Structural Pydantic models for CMS Hospital Price Transparency JSON.

These models are ingest-time shape checks for the JSON parser. They reject only
records whose containers cannot be exploded into Bronze rows. CMS value,
conditional, enum, and format validation is handled in dbt so malformed source
values can remain queryable in Bronze.
"""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

JsonSchemaFamily = str

PARSER_PROFILE_VERSIONS: dict[JsonSchemaFamily, str] = {
    "2.1": "2.1.0",
    "2.2": "2.2.1",
    "3.0": "3.0.0",
}


def normalize_json_schema_family(version: str | None) -> JsonSchemaFamily | None:
    """Normalize a CMS JSON version string to a parser schema family."""
    if version is None:
        return None

    cleaned = str(version).strip().lower()
    if not cleaned:
        return None
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]

    if cleaned.startswith("3.0"):
        return "3.0"
    if cleaned.startswith("2.2"):
        return "2.2"
    if cleaned.startswith("2.1"):
        return "2.1"
    return None


def parser_schema_version_for_family(
    family: JsonSchemaFamily | None,
) -> str | None:
    """Return the canonical CMS schema version backing a parser family."""
    if family is None:
        return None
    return PARSER_PROFILE_VERSIONS.get(family)


class CMSModel(BaseModel):
    """Common model settings for CMS JSON shape models."""

    model_config = ConfigDict(extra="allow")


def _scalar_to_text(value: Any) -> str | None:
    """Preserve any JSON scalar as text; reject containers."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        raise ValueError("Expected scalar value, not array/object")
    return str(value)


def _scalar_list_to_text(value: Any) -> list[str | None] | None:
    """Preserve a JSON array of scalars as text values."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("Expected array")
    return [_scalar_to_text(item) for item in value]


class Attestation(CMSModel):
    attestation: str | None
    confirm_attestation: str | None
    attester_name: str | None

    _scalar_fields = field_validator(
        "attestation",
        "confirm_attestation",
        "attester_name",
        mode="before",
    )(_scalar_to_text)


class HospitalLicensure(CMSModel):
    license_number: str | None = None
    state: str | None

    _scalar_fields = field_validator("license_number", "state", mode="before")(
        _scalar_to_text
    )


class DrugInformation(CMSModel):
    unit: str | None
    type: str | None

    _scalar_fields = field_validator("unit", "type", mode="before")(_scalar_to_text)


class CodeInformation(CMSModel):
    code: str | None
    type: str | None

    _scalar_fields = field_validator("code", "type", mode="before")(_scalar_to_text)


class ModifierPayerInformation(CMSModel):
    payer_name: str | None
    plan_name: str | None
    description: str | None

    _scalar_fields = field_validator(
        "payer_name",
        "plan_name",
        "description",
        mode="before",
    )(_scalar_to_text)


class PayersInformation(CMSModel):
    payer_name: str | None = None
    plan_name: str | None = None
    methodology: str | None = None
    additional_payer_notes: str | None = None
    standard_charge_dollar: str | None = None
    standard_charge_percentage: str | None = None
    standard_charge_algorithm: str | None = None
    estimated_amount: str | None = None
    median_amount: str | None = None
    tenth_percentile: str | None = Field(default=None, alias="10th_percentile")
    ninetieth_percentile: str | None = Field(default=None, alias="90th_percentile")
    count: str | None = None

    @field_validator(
        "payer_name",
        "plan_name",
        "methodology",
        "standard_charge_dollar",
        "standard_charge_percentage",
        "estimated_amount",
        "median_amount",
        "tenth_percentile",
        "ninetieth_percentile",
        "standard_charge_algorithm",
        "count",
        "additional_payer_notes",
        mode="before",
    )
    @classmethod
    def preserve_scalar_fields(cls, value: Any) -> str | None:
        return _scalar_to_text(value)


class StandardCharge(CMSModel):
    minimum: str | None = None
    maximum: str | None = None
    gross_charge: str | None = None
    discounted_cash: str | None = None
    setting: str | None
    modifier_code: list[str | None] | None = None
    payers_information: list[PayersInformation] | None = None
    additional_generic_notes: str | None = None
    billing_class: str | None = None

    @field_validator(
        "minimum",
        "maximum",
        "gross_charge",
        "discounted_cash",
        "setting",
        "additional_generic_notes",
        "billing_class",
        mode="before",
    )
    @classmethod
    def preserve_scalar_fields(cls, value: Any) -> str | None:
        return _scalar_to_text(value)

    @field_validator("modifier_code", mode="before")
    @classmethod
    def preserve_modifier_codes(cls, value: Any) -> list[str | None] | None:
        return _scalar_list_to_text(value)


class ModifierInformation(CMSModel):
    description: str | None
    code: str | None
    modifier_payer_information: list[ModifierPayerInformation]
    setting: str | None = None

    _scalar_fields = field_validator(
        "description",
        "code",
        "setting",
        mode="before",
    )(_scalar_to_text)


class StandardChargeInformation(CMSModel):
    description: str | None
    drug_information: DrugInformation | None = None
    code_information: list[CodeInformation]
    standard_charges: list[StandardCharge]

    _scalar_fields = field_validator("description", mode="before")(_scalar_to_text)


class GeneralContractProvisions(CMSModel):
    payer_name: str | None = None
    plan_name: str | None = None
    provisions: str | None = None

    _scalar_fields = field_validator(
        "payer_name",
        "plan_name",
        "provisions",
        mode="before",
    )(_scalar_to_text)


class CMSMRFJson(CMSModel):
    hospital_name: str | None
    last_updated_on: str | None
    version: str | None
    location_name: list[str]
    hospital_address: list[str]
    license_information: HospitalLicensure
    attestation: Attestation
    standard_charge_information: list[StandardChargeInformation]
    modifier_information: list[ModifierInformation] | None = None
    type_2_npi: list[str | None]
    financial_aid_policy: str | None = None
    general_contract_provisions: list[GeneralContractProvisions] | None = None

    @field_validator(
        "hospital_name",
        "last_updated_on",
        "version",
        "financial_aid_policy",
        mode="before",
    )
    @classmethod
    def preserve_scalar_fields(cls, value: Any) -> str | None:
        return _scalar_to_text(value)

    @field_validator("location_name", "hospital_address", "type_2_npi", mode="before")
    @classmethod
    def preserve_scalar_arrays(cls, value: Any) -> list[str | None] | None:
        return _scalar_list_to_text(value)

