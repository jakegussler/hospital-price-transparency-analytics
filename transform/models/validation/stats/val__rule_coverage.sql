with coverage as (
    select
        rule_id,
        case
            when rule_id in (
                'root_required_header_shape',
                'attestation_required_fields',
                'license_information_required_state',
                'last_updated_on_iso_date',
                'type_2_npi_ten_digit_numeric',
                'state_two_letter_format',
                'state_valid_usps_code',
                'attestation_text_exact',
                'attestation_confirmation_true',
                'csv_placeholder_headers_resolved',
                'general_contract_provisions_required_shape'
            ) then 'val__header_violations'
            when rule_id in (
                'standard_charge_information_required_shape',
                'required_arrays_non_empty'
            ) then 'val__charge_item_violations'
            when rule_id = 'modifier_information_required_shape'
                then 'val__modifier_violations'
            when rule_id in (
                'code_information_required_shape',
                'code_type_allowed_values',
                'code_type_family_specific_enum',
                'csv_code_pair_required'
            ) then 'val__code_violations'
            when rule_id in (
                'drug_information_required_shape_when_present',
                'drug_unit_numeric_parseable',
                'drug_unit_positive',
                'drug_type_allowed_values'
            ) then 'val__drug_violations'
            when rule_id = 'ndc_requires_drug_information' then 'val__charge_item_violations'
            when rule_id in (
                'standard_charge_required_setting_shape',
                'standard_charge_numeric_parseable',
                'standard_charge_numeric_positive',
                'setting_allowed_values',
                'charge_requires_any_standard_charge_value',
                'payer_dollar_requires_minimum_and_maximum',
                'billing_class_allowed_values'
            ) then 'val__standard_charge_violations'
            when rule_id in (
                'count_zero_requires_explanation',
                'payer_required_identity_and_methodology',
                'payer_numeric_parseable',
                'payer_numeric_positive',
                'methodology_allowed_values',
                'payer_requires_negotiated_charge',
                'methodology_other_requires_notes',
                'v2_2_percentage_or_algorithm_requires_estimated_amount',
                'v3_percentage_or_algorithm_requires_count',
                'v3_count_nonzero_requires_allowed_amounts',
                'v3_count_allowed_format',
                'csv_payer_identity_required_with_rate'
            ) then 'val__payer_rate_violations'
            when rule_id = 'csv_modifier_without_item_minimum_information' then 'val__modifier_violations'
            when rule_id = 'required_text_non_empty' then 'val__all_violations'
            else null
        end as primary_model,
        case
            when rule_id = 'modifier_information_required_shape'
                then 'implemented_where_bronze_evidence_exists'
            when rule_id in (
                'standard_charge_information_required_shape',
                'required_arrays_non_empty'
            ) then 'implemented_plus_json_parse_diagnostics'
            else 'implemented'
        end as implementation_status,
        case
            when rule_id in (
                'standard_charge_information_required_shape',
                'required_arrays_non_empty'
            ) then 'Accepted Bronze rows are checked where row evidence exists; quarantined JSON rows are represented in val__structural_parse_violations.'
            when rule_id = 'general_contract_provisions_required_shape' then 'General contract provision rows are emitted source-faithfully by the parser (JSON array objects and the flat CSV column), so val__header_violations flags missing/blank provisions at the file grain.'
            when rule_id = 'modifier_information_required_shape' then 'Modifier rows are checked when the optional modifier Bronze tables are present; parser diagnostics cover quarantined JSON records.'
            else 'Rule has row-level dbt checks.'
        end as coverage_notes
    from {{ ref('cms_validation_rules') }}
)

select
    r.rule_id,
    r.rule_name,
    r.grain,
    r.severity,
    r.applies_to_formats,
    c.primary_model,
    c.implementation_status,
    c.coverage_notes
from {{ ref('cms_validation_rules') }} r
left join coverage c
    on r.rule_id = c.rule_id
