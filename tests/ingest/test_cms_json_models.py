"""Tests for hpt.ingest.cms_json_models — Pydantic validation models."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from hpt.ingest.cms_json_models import (
    CMSMRFJson,
    DrugInformation,
    HospitalLicensure,
    PayersInformation,
    StandardCharge,
    StandardChargeInformation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_payer(**overrides) -> dict:
    base = {
        "payer_name": "Aetna",
        "plan_name": "PPO",
        "methodology": "fee schedule",
        "standard_charge_dollar": 150.0,
    }
    base.update(overrides)
    return base


def _valid_charge(**overrides) -> dict:
    base = {
        "setting": "outpatient",
        "gross_charge": 200.0,
        "payers_information": [_valid_payer()],
        "minimum": 100.0,
        "maximum": 300.0,
    }
    base.update(overrides)
    return base


def _valid_sci(**overrides) -> dict:
    base = {
        "description": "X-Ray",
        "code_information": [{"code": "CPT001", "type": "CPT"}],
        "standard_charges": [_valid_charge()],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# HospitalLicensure
# ---------------------------------------------------------------------------


class TestHospitalLicensure:
    def test_state_normalized_to_uppercase(self):
        lic = HospitalLicensure.model_validate({"state": "fl", "license_number": "L1"})
        assert lic.state == "FL"

    def test_state_invalid_length_raises(self):
        with pytest.raises(ValidationError, match="2-letter"):
            HospitalLicensure.model_validate({"state": "FLA"})

    def test_state_non_alpha_raises(self):
        with pytest.raises(ValidationError, match="2-letter"):
            HospitalLicensure.model_validate({"state": "F1"})

    def test_license_number_optional(self):
        lic = HospitalLicensure.model_validate({"state": "TX"})
        assert lic.license_number is None


# ---------------------------------------------------------------------------
# DrugInformation
# ---------------------------------------------------------------------------


class TestDrugInformation:
    def test_valid(self):
        drug = DrugInformation.model_validate({"unit": 10.0, "type": "ML"})
        assert drug.unit == Decimal("10")
        assert drug.type.value == "ML"

    def test_unit_zero_raises(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            DrugInformation.model_validate({"unit": 0, "type": "ML"})

    def test_unit_negative_raises(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            DrugInformation.model_validate({"unit": -1.0, "type": "ML"})

    def test_unit_accepts_string_numeric(self):
        drug = DrugInformation.model_validate({"unit": "5.5", "type": "GR"})
        assert drug.unit == Decimal("5.5")


# ---------------------------------------------------------------------------
# PayersInformation — field validators
# ---------------------------------------------------------------------------


class TestPayersInformationFieldValidators:
    def test_count_int_1_through_10_normalized(self):
        payer = PayersInformation.model_validate(
            {**_valid_payer(), "count": 5}
        )
        assert payer.count == "1 through 10"

    def test_count_int_11_plus_as_string(self):
        payer = PayersInformation.model_validate(
            {**_valid_payer(), "count": 15}
        )
        assert payer.count == "15"

    def test_count_int_0_as_string(self):
        payer = PayersInformation.model_validate(
            {**_valid_payer(), "count": 0}
        )
        assert payer.count == "0"

    def test_count_empty_string_normalized_to_none(self):
        payer = PayersInformation.model_validate(
            {**_valid_payer(), "count": ""}
        )
        assert payer.count is None

    def test_decimal_fields_accept_string_numeric(self):
        payer = PayersInformation.model_validate(
            {**_valid_payer(), "standard_charge_dollar": "12.50"}
        )
        assert payer.standard_charge_dollar == Decimal("12.50")

    def test_decimal_field_zero_raises(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            PayersInformation.model_validate(
                {**_valid_payer(), "standard_charge_dollar": 0}
            )

    def test_decimal_field_boolean_raises(self):
        with pytest.raises(ValidationError, match="Boolean"):
            PayersInformation.model_validate(
                {**_valid_payer(), "standard_charge_dollar": True}
            )


# ---------------------------------------------------------------------------
# PayersInformation — model validators
# ---------------------------------------------------------------------------


class TestPayersInformationModelValidators:
    def test_no_charge_value_raises(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
        }
        with pytest.raises(ValidationError, match="negotiated charge"):
            PayersInformation.model_validate(data)

    def test_methodology_other_requires_notes(self):
        data = {
            **_valid_payer(),
            "methodology": "other",
        }
        with pytest.raises(ValidationError, match="additional_payer_notes"):
            PayersInformation.model_validate(data)

    def test_methodology_other_with_notes_valid(self):
        data = {
            **_valid_payer(),
            "methodology": "other",
            "additional_payer_notes": "See contract",
        }
        payer = PayersInformation.model_validate(data)
        assert payer.additional_payer_notes == "See contract"

    def test_percentage_requires_count(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_percentage": 80.0,
        }
        with pytest.raises(ValidationError, match="count is required"):
            PayersInformation.model_validate(data)

    def test_percentage_nonzero_count_requires_percentiles(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_percentage": 80.0,
            "count": "15",
        }
        with pytest.raises(ValidationError, match="median_amount"):
            PayersInformation.model_validate(data)

    def test_percentage_count_zero_no_percentiles_required(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_percentage": 80.0,
            "count": "0",
            "additional_payer_notes": "Insufficient data",
        }
        # count=0 → percentiles not required
        payer = PayersInformation.model_validate(data)
        assert payer.count == "0"

    def test_algorithm_requires_count(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_algorithm": "see contract",
        }
        with pytest.raises(ValidationError, match="count is required"):
            PayersInformation.model_validate(data)

    def test_v2_2_algorithm_with_estimated_amount_valid_without_count(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_algorithm": "see contract",
            "estimated_amount": 125.50,
        }
        payer = PayersInformation.model_validate(data, context={"schema_family": "2.2"})
        assert payer.estimated_amount == Decimal("125.5")
        assert payer.count is None

    def test_v2_2_algorithm_without_estimated_amount_raises(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_algorithm": "see contract",
        }
        with pytest.raises(ValidationError, match="estimated_amount"):
            PayersInformation.model_validate(data, context={"schema_family": "2.2"})

    def test_v3_algorithm_with_count_and_percentiles_valid(self):
        data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_algorithm": "see contract",
            "count": "15",
            "median_amount": 100.0,
            "10th_percentile": 80.0,
            "90th_percentile": 120.0,
        }
        payer = PayersInformation.model_validate(data, context={"schema_family": "3.0"})
        assert payer.count == "15"
        assert payer.median_amount == Decimal("100.0")


# ---------------------------------------------------------------------------
# StandardCharge — model validators
# ---------------------------------------------------------------------------


class TestStandardChargeModelValidators:
    def test_no_gross_or_discounted_or_payer_raises(self):
        data = {
            "setting": "outpatient",
        }
        with pytest.raises(ValidationError, match="at least one"):
            StandardCharge.model_validate(data)

    def test_gross_charge_alone_is_sufficient(self):
        charge = StandardCharge.model_validate(
            {"setting": "outpatient", "gross_charge": 200.0}
        )
        assert charge.gross_charge == Decimal("200")

    def test_payer_dollar_requires_min_max(self):
        data = {
            "setting": "outpatient",
            "payers_information": [_valid_payer()],
            # min/max are missing
        }
        with pytest.raises(ValidationError, match="minimum and maximum"):
            StandardCharge.model_validate(data)

    def test_payer_dollar_with_min_max_valid(self):
        data = _valid_charge()
        charge = StandardCharge.model_validate(data)
        assert charge.minimum == Decimal("100")
        assert charge.maximum == Decimal("300")

    def test_count_zero_percentage_requires_notes(self):
        payer_data = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            "standard_charge_percentage": 80.0,
            "count": "0",
            # No notes at payer or charge level
        }
        data = {
            "setting": "outpatient",
            "payers_information": [payer_data],
            # no additional_generic_notes either
        }
        with pytest.raises(ValidationError, match="explanation"):
            StandardCharge.model_validate(data)


# ---------------------------------------------------------------------------
# StandardChargeInformation — model validators
# ---------------------------------------------------------------------------


class TestStandardChargeInformation:
    def test_ndc_code_requires_drug_information(self):
        data = {
            "description": "Drug",
            "code_information": [{"code": "NDC001", "type": "NDC"}],
            "standard_charges": [_valid_charge()],
        }
        with pytest.raises(ValidationError, match="drug_information"):
            StandardChargeInformation.model_validate(data)

    def test_ndc_code_with_drug_information_valid(self):
        data = {
            "description": "Drug",
            "code_information": [{"code": "NDC001", "type": "NDC"}],
            "drug_information": {"unit": 10.0, "type": "ML"},
            "standard_charges": [_valid_charge()],
        }
        sci = StandardChargeInformation.model_validate(data)
        assert sci.drug_information is not None

    def test_non_ndc_without_drug_information_valid(self):
        sci = StandardChargeInformation.model_validate(_valid_sci())
        assert sci.drug_information is None

    def test_v2_1_ndc_without_drug_information_valid(self):
        data = {
            "description": "Drug",
            "code_information": [{"code": "NDC001", "type": "NDC"}],
            "standard_charges": [_valid_charge()],
        }
        sci = StandardChargeInformation.model_validate(data, context={"schema_family": "2.1"})
        assert sci.drug_information is None

    def test_v2_2_ndc_without_drug_information_raises(self):
        data = {
            "description": "Drug",
            "code_information": [{"code": "NDC001", "type": "NDC"}],
            "standard_charges": [_valid_charge()],
        }
        with pytest.raises(ValidationError, match="drug_information"):
            StandardChargeInformation.model_validate(data, context={"schema_family": "2.2"})


# ---------------------------------------------------------------------------
# CMSMRFJson — field validators
# ---------------------------------------------------------------------------


def _valid_cms_mrf(**overrides) -> dict:
    base = {
        "hospital_name": "Test Hospital",
        "last_updated_on": "2025-01-01",
        "version": "3.0.0",
        "license_information": {"state": "FL"},
        "attestation": {
            "attestation": "I attest",
            "confirm_attestation": True,
            "attester_name": "Jane",
        },
        "location_name": ["Main"],
        "hospital_address": ["123 Main St"],
        "type_2_npi": [],
        "standard_charge_information": [_valid_sci()],
    }
    base.update(overrides)
    return base


class TestCMSMRFJson:
    def test_valid_document(self):
        doc = CMSMRFJson.model_validate(_valid_cms_mrf())
        assert doc.hospital_name == "Test Hospital"

    def test_npi_must_be_10_digit_numeric(self):
        doc = CMSMRFJson.model_validate(
            _valid_cms_mrf(type_2_npi=["1234567890"])
        )
        assert doc.type_2_npi == ["1234567890"]

    def test_npi_non_numeric_raises(self):
        with pytest.raises(ValidationError, match="10-digit numeric"):
            CMSMRFJson.model_validate(_valid_cms_mrf(type_2_npi=["ABC1234567"]))

    def test_npi_wrong_length_raises(self):
        with pytest.raises(ValidationError, match="10-digit numeric"):
            CMSMRFJson.model_validate(_valid_cms_mrf(type_2_npi=["12345"]))

    def test_last_updated_on_invalid_format_raises(self):
        with pytest.raises(ValidationError, match="ISO date"):
            CMSMRFJson.model_validate(_valid_cms_mrf(last_updated_on="01/01/2025"))

    def test_last_updated_on_valid_format(self):
        doc = CMSMRFJson.model_validate(_valid_cms_mrf(last_updated_on="2025-06-15"))
        assert doc.last_updated_on == "2025-06-15"
