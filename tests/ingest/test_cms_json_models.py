"""Tests for structural-only CMS JSON Pydantic models."""

from __future__ import annotations

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


class TestHospitalLicensure:
    def test_state_is_preserved_as_raw_text(self):
        lic = HospitalLicensure.model_validate({"state": "fl", "license_number": "L1"})
        assert lic.state == "fl"

    def test_state_format_is_not_validated(self):
        assert HospitalLicensure.model_validate({"state": "FLA"}).state == "FLA"
        assert HospitalLicensure.model_validate({"state": "F1"}).state == "F1"

    def test_state_container_shape_raises(self):
        with pytest.raises(ValidationError, match="Expected scalar"):
            HospitalLicensure.model_validate({"state": ["FL"]})

    def test_license_number_optional(self):
        lic = HospitalLicensure.model_validate({"state": "TX"})
        assert lic.license_number is None


class TestDrugInformation:
    def test_valid_scalars_are_preserved_as_text(self):
        drug = DrugInformation.model_validate({"unit": 10.0, "type": "ML"})
        assert drug.unit == "10.0"
        assert drug.type == "ML"

    def test_invalid_value_level_drug_fields_validate(self):
        assert DrugInformation.model_validate({"unit": 0, "type": "bad"}).unit == "0"
        assert DrugInformation.model_validate({"unit": -1.0, "type": "bad"}).unit == "-1.0"
        drug = DrugInformation.model_validate({"unit": "not numeric", "type": "bad"})
        assert drug.unit == "not numeric"

    def test_required_keys_are_still_required(self):
        with pytest.raises(ValidationError):
            DrugInformation.model_validate({"unit": 10.0})

    def test_scalar_shape_is_required(self):
        with pytest.raises(ValidationError, match="Expected scalar"):
            DrugInformation.model_validate({"unit": {"amount": 10}, "type": "ML"})


class TestPayersInformation:
    def test_value_level_fields_are_preserved_as_text(self):
        payer = PayersInformation.model_validate(
            {
                "payer_name": "Aetna",
                "plan_name": "PPO",
                "methodology": "not a CMS methodology",
                "standard_charge_dollar": 0,
                "standard_charge_percentage": "not numeric",
                "count": 5,
                "10th_percentile": -1,
                "90th_percentile": True,
            }
        )

        assert payer.methodology == "not a CMS methodology"
        assert payer.standard_charge_dollar == "0"
        assert payer.standard_charge_percentage == "not numeric"
        assert payer.count == "5"
        assert payer.tenth_percentile == "-1"
        assert payer.ninetieth_percentile == "True"

    def test_conditional_requirements_are_not_validated(self):
        assert PayersInformation.model_validate(
            {"payer_name": "Aetna", "plan_name": "PPO", "methodology": "fee schedule"}
        )
        assert PayersInformation.model_validate(
            {"methodology": "other", "standard_charge_dollar": 100}
        )
        assert PayersInformation.model_validate(
            {
                "methodology": "fee schedule",
                "standard_charge_percentage": 80.0,
            }
        )

    def test_missing_payer_identity_is_allowed_for_dbt_validation(self):
        payer = PayersInformation.model_validate({"standard_charge_dollar": 10})
        assert payer.payer_name is None
        assert payer.plan_name is None
        assert payer.methodology is None

    def test_scalar_shape_is_required_for_payer_fields(self):
        with pytest.raises(ValidationError, match="Expected scalar"):
            PayersInformation.model_validate({"payer_name": ["Aetna"]})


class TestStandardCharge:
    def test_numeric_and_enum_values_are_preserved_as_text(self):
        charge = StandardCharge.model_validate(
            {
                "setting": "bad setting",
                "gross_charge": -200.0,
                "minimum": "not numeric",
                "maximum": 0,
            }
        )

        assert charge.setting == "bad setting"
        assert charge.gross_charge == "-200.0"
        assert charge.minimum == "not numeric"
        assert charge.maximum == "0"

    def test_conditional_requirements_are_not_validated(self):
        assert StandardCharge.model_validate({"setting": "outpatient"})
        assert StandardCharge.model_validate(
            {"setting": "outpatient", "payers_information": [_valid_payer()]}
        )
        assert StandardCharge.model_validate(
            {
                "setting": "outpatient",
                "payers_information": [
                    {
                        "methodology": "fee schedule",
                        "standard_charge_percentage": 80.0,
                        "count": "0",
                    }
                ],
            }
        )

    def test_setting_key_is_still_required(self):
        with pytest.raises(ValidationError):
            StandardCharge.model_validate({"gross_charge": 200})

    def test_array_shape_is_required_for_payers_information(self):
        with pytest.raises(ValidationError):
            StandardCharge.model_validate(
                {"setting": "outpatient", "payers_information": {"payer_name": "Aetna"}}
            )

    def test_modifier_code_array_must_contain_scalars(self):
        with pytest.raises(ValidationError, match="Expected scalar"):
            StandardCharge.model_validate(
                {"setting": "outpatient", "modifier_code": [{"code": "26"}]}
            )


class TestStandardChargeInformation:
    def test_ndc_conditional_drug_requirement_is_not_validated(self):
        sci = StandardChargeInformation.model_validate(
            {
                "description": "Drug",
                "code_information": [{"code": "NDC001", "type": "NDC"}],
                "standard_charges": [_valid_charge()],
            }
        )
        assert sci.drug_information is None

    def test_drug_information_shape_still_required_when_present(self):
        with pytest.raises(ValidationError):
            StandardChargeInformation.model_validate(
                {
                    "description": "Drug",
                    "code_information": [{"code": "NDC001", "type": "NDC"}],
                    "drug_information": {"unit": 10.0},
                    "standard_charges": [_valid_charge()],
                }
            )

    def test_required_containers_are_still_required(self):
        with pytest.raises(ValidationError):
            StandardChargeInformation.model_validate({"description": "Bad"})

    def test_required_containers_must_be_arrays(self):
        with pytest.raises(ValidationError):
            StandardChargeInformation.model_validate(
                {
                    "description": "Bad",
                    "code_information": {"code": "CPT001", "type": "CPT"},
                    "standard_charges": [_valid_charge()],
                }
            )

    def test_non_ndc_without_drug_information_valid(self):
        sci = StandardChargeInformation.model_validate(_valid_sci())
        assert sci.drug_information is None


class TestCMSMRFJson:
    def test_valid_document(self):
        doc = CMSMRFJson.model_validate(_valid_cms_mrf())
        assert doc.hospital_name == "Test Hospital"

    def test_header_format_values_are_not_validated(self):
        doc = CMSMRFJson.model_validate(
            _valid_cms_mrf(
                type_2_npi=["ABC1234567", "12345"],
                last_updated_on="01/01/2025",
            )
        )

        assert doc.type_2_npi == ["ABC1234567", "12345"]
        assert doc.last_updated_on == "01/01/2025"

    def test_header_arrays_must_be_arrays(self):
        with pytest.raises(ValidationError, match="Expected array"):
            CMSMRFJson.model_validate(_valid_cms_mrf(type_2_npi="1234567890"))

    def test_scalar_header_fields_must_not_be_containers(self):
        with pytest.raises(ValidationError, match="Expected scalar"):
            CMSMRFJson.model_validate(_valid_cms_mrf(last_updated_on=["2025-01-01"]))
