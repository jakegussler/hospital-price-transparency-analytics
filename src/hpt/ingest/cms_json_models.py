"""Pydantic models for CMS Hospital Price Transparency JSON (v3.0).

These models are intended for ingest-time validation of machine-readable files
before records are persisted downstream.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CMSModel(BaseModel):
    """Common model settings for CMS JSON validation models."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)


class Setting(str, Enum):
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    BOTH = "both"


class DrugMeasurementType(str, Enum):
    GR = "GR"
    ME = "ME"
    ML = "ML"
    UN = "UN"
    F2 = "F2"
    EA = "EA"
    GM = "GM"


class StandardChargeMethodology(str, Enum):
    CASE_RATE = "case rate"
    FEE_SCHEDULE = "fee schedule"
    PERCENT_OF_TOTAL_BILLED_CHARGES = "percent of total billed charges"
    PER_DIEM = "per diem"
    OTHER = "other"


class CodeType(str, Enum):
    CPT = "CPT"
    NDC = "NDC"
    HCPCS = "HCPCS"
    RC = "RC"
    ICD = "ICD"
    DRG = "DRG"
    MS_DRG = "MS-DRG"
    R_DRG = "R-DRG"
    S_DRG = "S-DRG"
    APS_DRG = "APS-DRG"
    AP_DRG = "AP-DRG"
    APR_DRG = "APR-DRG"
    APC = "APC"
    LOCAL = "LOCAL"
    EAPG = "EAPG"
    HIPPS = "HIPPS"
    CDT = "CDT"
    CDM = "CDM"
    TRIS_DRG = "TRIS-DRG"
    CMG = "CMG"
    MS_LTC_DRG = "MS-LTC-DRG"


def _to_optional_decimal(value: Any) -> Decimal | None:
    """Convert numeric-like values to Decimal and normalize empty values to None."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid numeric inputs")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "":
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Could not parse numeric value: {value!r}") from exc
    raise ValueError(f"Unsupported numeric value type: {type(value).__name__}")


def _ensure_positive_decimal(value: Decimal | None) -> Decimal | None:
    """Numeric elements in CMS JSON must be positive when present."""
    if value is None:
        return None
    if value <= 0:
        raise ValueError("Numeric values must be greater than zero")
    return value


class Attestation(CMSModel):
    attestation: str
    confirm_attestation: bool
    attester_name: str


class HospitalLicensure(CMSModel):
    license_number: str | None = None
    state: str

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise ValueError("state must be a 2-letter code")
        return value.upper()


class DrugInformation(CMSModel):
    unit: Decimal
    type: DrugMeasurementType

    @field_validator("unit", mode="before")
    @classmethod
    def parse_unit(cls, value: Any) -> Decimal | None:
        return _to_optional_decimal(value)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: Decimal) -> Decimal:
        maybe_value = _ensure_positive_decimal(value)
        assert maybe_value is not None
        return maybe_value


class CodeInformation(CMSModel):
    code: str
    type: CodeType


class ModifierPayerInformation(CMSModel):
    payer_name: str
    plan_name: str
    description: str


class PayersInformation(CMSModel):
    payer_name: str
    plan_name: str
    methodology: StandardChargeMethodology
    additional_payer_notes: str | None = None
    standard_charge_dollar: Decimal | None = None
    standard_charge_percentage: Decimal | None = None
    standard_charge_algorithm: str | None = None
    median_amount: Decimal | None = None
    tenth_percentile: Decimal | None = Field(default=None, alias="10th_percentile")
    ninetieth_percentile: Decimal | None = Field(default=None, alias="90th_percentile")
    count: str | None = None

    @field_validator(
        "standard_charge_dollar",
        "standard_charge_percentage",
        "median_amount",
        "tenth_percentile",
        "ninetieth_percentile",
        mode="before",
    )
    @classmethod
    def parse_decimal_fields(cls, value: Any) -> Decimal | None:
        return _to_optional_decimal(value)

    @field_validator(
        "standard_charge_dollar",
        "standard_charge_percentage",
        "median_amount",
        "tenth_percentile",
        "ninetieth_percentile",
    )
    @classmethod
    def validate_decimal_fields(cls, value: Decimal | None) -> Decimal | None:
        return _ensure_positive_decimal(value)

    @field_validator("standard_charge_algorithm", "additional_payer_notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return str(value)

    @field_validator("count", mode="before")
    @classmethod
    def normalize_count(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, int):
            if value == 0:
                return "0"
            if 1 <= value <= 10:
                return "1 through 10"
            if value >= 11:
                return str(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "":
                return None
            return cleaned
        raise ValueError("count must be a string or integer")

    @field_validator("count")
    @classmethod
    def validate_count(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "0" or value == "1 through 10":
            return value
        if value.isdigit():
            numeric = int(value)
            if numeric >= 11:
                return value
            raise ValueError("count values 1-10 must be encoded as '1 through 10'")
        raise ValueError("count must be '0', '1 through 10', or a whole number >= 11")

    @model_validator(mode="after")
    def validate_conditional_requirements(self) -> PayersInformation:
        has_dollar = self.standard_charge_dollar is not None
        has_percentage = self.standard_charge_percentage is not None
        has_algorithm = self.standard_charge_algorithm is not None

        if not any([has_dollar, has_percentage, has_algorithm]):
            raise ValueError(
                "At least one payer-specific negotiated charge is required "
                "(dollar, percentage, or algorithm)."
            )

        if self.methodology == StandardChargeMethodology.OTHER and not self.additional_payer_notes:
            raise ValueError("additional_payer_notes is required when methodology is 'other'")

        if has_percentage or has_algorithm:
            if self.count is None:
                raise ValueError(
                    "count is required when standard_charge_percentage or "
                    "standard_charge_algorithm is present"
                )
            if self.count != "0":
                if any(
                    value is None
                    for value in (
                        self.median_amount,
                        self.tenth_percentile,
                        self.ninetieth_percentile,
                    )
                ):
                    raise ValueError(
                        "median_amount, 10th_percentile, and 90th_percentile are "
                        "required when percentage/algorithm is present and count is not '0'"
                    )
        return self


class StandardCharge(CMSModel):
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    gross_charge: Decimal | None = None
    discounted_cash: Decimal | None = None
    setting: Setting
    modifier_code: list[str] | None = None
    payers_information: list[PayersInformation] | None = None
    additional_generic_notes: str | None = None
    billing_class: str | None = None

    @field_validator("minimum", "maximum", "gross_charge", "discounted_cash", mode="before")
    @classmethod
    def parse_numeric_fields(cls, value: Any) -> Decimal | None:
        return _to_optional_decimal(value)

    @field_validator("minimum", "maximum", "gross_charge", "discounted_cash")
    @classmethod
    def validate_numeric_fields(cls, value: Decimal | None) -> Decimal | None:
        return _ensure_positive_decimal(value)

    @field_validator("additional_generic_notes", mode="before")
    @classmethod
    def normalize_notes(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return str(value)

    @model_validator(mode="after")
    def validate_conditional_requirements(self) -> StandardCharge:
        payer_items = self.payers_information or []
        has_payer_specific_data = any(
            item.standard_charge_dollar is not None
            or item.standard_charge_percentage is not None
            or item.standard_charge_algorithm is not None
            for item in payer_items
        )
        if (
            self.gross_charge is None
            and self.discounted_cash is None
            and not has_payer_specific_data
        ):
            raise ValueError(
                "Each standard charge must include at least one of gross_charge, "
                "discounted_cash, or payer-specific negotiated charge data."
            )

        if any(item.standard_charge_dollar is not None for item in payer_items):
            if self.minimum is None or self.maximum is None:
                raise ValueError(
                    "minimum and maximum are required when payer-specific dollar "
                    "charges are present"
                )

        for item in payer_items:
            uses_percentage_or_algorithm = (
                item.standard_charge_percentage is not None
                or item.standard_charge_algorithm is not None
            )
            if uses_percentage_or_algorithm and item.count == "0":
                if not (item.additional_payer_notes or self.additional_generic_notes):
                    raise ValueError(
                        "When count is '0' for percentage/algorithm charges, include an "
                        "explanation in additional_payer_notes or additional_generic_notes."
                    )
        return self


class ModifierInformation(CMSModel):
    description: str
    code: str
    modifier_payer_information: list[ModifierPayerInformation]
    setting: Setting | None = None


class StandardChargeInformation(CMSModel):
    description: str
    drug_information: DrugInformation | None = None
    code_information: list[CodeInformation]
    standard_charges: list[StandardCharge]

    @model_validator(mode="after")
    def validate_ndc_drug_requirements(self) -> StandardChargeInformation:
        has_ndc = any(item.type == CodeType.NDC for item in self.code_information)
        if has_ndc and self.drug_information is None:
            raise ValueError(
                "drug_information is required when any code_information.type is 'NDC'"
            )
        return self


class GeneralContractProvisions(CMSModel):
    payer_name: str | None = None
    plan_name: str | None = None
    provisions: str


class CMSMRFJson(CMSModel):
    hospital_name: str
    last_updated_on: str
    version: str
    location_name: list[str]
    hospital_address: list[str]
    license_information: HospitalLicensure
    attestation: Attestation
    standard_charge_information: list[StandardChargeInformation]
    modifier_information: list[ModifierInformation] | None = None
    type_2_npi: list[str]
    financial_aid_policy: str | None = None
    general_contract_provisions: list[GeneralContractProvisions] | None = None

    @field_validator("type_2_npi")
    @classmethod
    def validate_type_2_npi(cls, value: list[str]) -> list[str]:
        cleaned_values: list[str] = []
        for npi in value:
            normalized = npi.strip()
            if not normalized.isdigit() or len(normalized) != 10:
                raise ValueError("Each type_2_npi value must be a 10-digit numeric string")
            cleaned_values.append(normalized)
        return cleaned_values

    @field_validator("last_updated_on")
    @classmethod
    def validate_last_updated_on(cls, value: str) -> str:
        if len(value) != 10 or value[4] != "-" or value[7] != "-":
            raise ValueError("last_updated_on must be in ISO date format YYYY-MM-DD")
        return value

