{% macro hpt_schema_family_from_version(expression) -%}
    case
        when {{ hpt_clean_display_text(expression) }} like '2.1%' then '2.1'
        when {{ hpt_clean_display_text(expression) }} like '2.2%' then '2.2'
        when {{ hpt_clean_display_text(expression) }} like '3.%' then '3.0'
        else null
    end
{%- endmacro %}

{% macro hpt_source_format_family(expression) -%}
    case
        when lower(cast({{ expression }} as varchar)) = 'json' then 'json'
        when lower(cast({{ expression }} as varchar)) like 'csv%' then 'csv'
        else lower(cast({{ expression }} as varchar))
    end
{%- endmacro %}

{% macro hpt_validation_common_columns() -%}
    validation_violation_id,
    snapshot_id,
    hospital_id,
    source_format,
    source_format_family,
    reported_schema_family,
    source_charge_item_id,
    source_standard_charge_id,
    payer_ordinal,
    row_ordinal,
    source_rate_ordinal,
    code_ordinal,
    modifier_code_id,
    npi_ordinal,
    provision_ordinal,
    modifier_payer_ordinal,
    structural_section,
    record_ordinal,
    rule_id,
    rule_name,
    severity,
    grain,
    disposition,
    column_name,
    raw_value,
    diagnostic_type,
    message,
    excludes_from_silver,
    cms_citation
{%- endmacro %}
