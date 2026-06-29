-- Emit value and conditional-rule violations for each standard-charge context.
-- The normalized JSON+CSV charge grain is built once in
-- val_int__standard_charge_grain; here we scan it a single time and emit one
-- row per (charge, violated rule) via a struct list + unnest, instead of
-- re-scanning the grain once per rule. See docs/cleanup.md.
{% set standard_charge_numeric_columns = [
    ('gross_charge', 'gross_charge'),
    ('discounted_cash', 'discounted_cash'),
    ('minimum', 'minimum'),
    ('maximum', 'maximum')
] %}

with charges as (
    select * from {{ hpt_scoped_ref('val_int__standard_charge_grain') }}
),

evaluated as (
    -- One scan of the charge grain. Each rule contributes a struct to the list
    -- when it fires (and NULL otherwise); list_filter drops the misses.
    select
        c.*,
        list_filter([
            {% for raw_column, public_name in standard_charge_numeric_columns %}
            -- Numeric parseability and positivity for {{ public_name }}.
            case
                when {{ hpt_clean_display_text('raw_' ~ raw_column) }} is not null
                    and {{ hpt_safe_decimal('raw_' ~ raw_column) }} is null
                then struct_pack(
                    rule_id := 'standard_charge_numeric_parseable',
                    column_name := '{{ public_name }}',
                    raw_value := cast(raw_{{ raw_column }} as varchar),
                    diagnostic_type := 'numeric_cast_failed',
                    message := '{{ public_name }} is non-empty but cannot be cast to decimal(18,4).'
                )
            end,
            case
                when {{ hpt_safe_decimal('raw_' ~ raw_column) }} is not null
                    and {{ hpt_safe_decimal('raw_' ~ raw_column) }} <= 0
                then struct_pack(
                    rule_id := 'standard_charge_numeric_positive',
                    column_name := '{{ public_name }}',
                    raw_value := cast(raw_{{ raw_column }} as varchar),
                    diagnostic_type := 'numeric_not_positive',
                    message := '{{ public_name }} must be greater than zero.'
                )
            end,
            {% endfor %}
            -- Required shape and accepted-value rules for setting.
            case
                when clean_setting is null
                then struct_pack(
                    rule_id := 'standard_charge_required_setting_shape',
                    column_name := 'setting',
                    raw_value := cast(raw_setting as varchar),
                    diagnostic_type := 'required_field_missing',
                    message := 'Standard charge setting is required.'
                )
            end,
            case
                when clean_setting is not null
                    and clean_setting not in ('inpatient', 'outpatient', 'both')
                then struct_pack(
                    rule_id := 'setting_allowed_values',
                    column_name := 'setting',
                    raw_value := cast(raw_setting as varchar),
                    diagnostic_type := 'accepted_value_invalid',
                    message := 'Setting must be inpatient, outpatient, or both.'
                )
            end,
            -- Recommended-value advisory for billing_class.
            case
                when clean_billing_class is not null
                    and clean_billing_class not in ('professional', 'facility', 'both')
                then struct_pack(
                    rule_id := 'billing_class_allowed_values',
                    column_name := 'billing_class',
                    raw_value := cast(raw_billing_class as varchar),
                    diagnostic_type := 'accepted_value_warn',
                    message := 'Billing class is populated outside the documented recommended values.'
                )
            end,
            -- Conditional charge-value and payer-dollar rules.
            case
                when {{ hpt_clean_display_text('raw_gross_charge') }} is null
                    and {{ hpt_clean_display_text('raw_discounted_cash') }} is null
                    and not has_payer_dollar
                    and not has_payer_percentage
                    and not has_payer_algorithm
                then struct_pack(
                    rule_id := 'charge_requires_any_standard_charge_value',
                    column_name := 'standard_charge_values',
                    raw_value := concat(
                        'gross=', coalesce(raw_gross_charge, '<null>'),
                        '; discounted_cash=', coalesce(raw_discounted_cash, '<null>'),
                        '; payer_dollar=', cast(has_payer_dollar as varchar),
                        '; payer_percentage=', cast(has_payer_percentage as varchar),
                        '; payer_algorithm=', cast(has_payer_algorithm as varchar)
                    ),
                    diagnostic_type := 'conditional_required_value_missing',
                    message := 'A standard charge must have gross, discounted cash, or payer-specific negotiated charge data.'
                )
            end,
            case
                when has_payer_dollar
                    and (
                        {{ hpt_clean_display_text('raw_minimum') }} is null
                        or {{ hpt_clean_display_text('raw_maximum') }} is null
                    )
                then struct_pack(
                    rule_id := 'payer_dollar_requires_minimum_and_maximum',
                    column_name := case
                        when {{ hpt_clean_display_text('raw_minimum') }} is null then 'minimum'
                        else 'maximum'
                    end,
                    raw_value := concat('minimum=', coalesce(raw_minimum, '<null>'), '; maximum=', coalesce(raw_maximum, '<null>')),
                    diagnostic_type := 'conditional_required_field_missing',
                    message := 'Payer negotiated dollar charge requires parent minimum and maximum.'
                )
            end
        ], x -> x is not null) as rule_hits
    from charges c
),

violations as (
    select
        e.snapshot_id,
        e.hospital_id,
        e.source_format,
        e.source_format_family,
        e.reported_schema_family,
        e.source_charge_item_id,
        e.source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        e.row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        hit.rule_id,
        hit.column_name,
        hit.raw_value,
        hit.diagnostic_type,
        hit.message
    from evaluated e
    cross join unnest(e.rule_hits) as t(hit)
),

deduped as (
    -- JSON payer fanout can repeat the same parent-level finding; preserve one
    -- violation per source charge, rule, column, and raw value.
    select *
    from violations
    qualify row_number() over (
        partition by
            snapshot_id,
            source_format_family,
            coalesce(source_charge_item_id, ''),
            coalesce(source_standard_charge_id, ''),
            coalesce(cast(row_ordinal as varchar), ''),
            rule_id,
            column_name,
            coalesce(raw_value, '')
        order by 1
    ) = 1
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'standard_charge'", 'v.rule_id', 'v.column_name',
            'v.source_charge_item_id', 'v.source_standard_charge_id',
            'v.row_ordinal', 'v.raw_value'
        ]) }} as validation_violation_id,
        v.snapshot_id,
        v.hospital_id,
        v.source_format,
        v.source_format_family,
        v.reported_schema_family,
        v.source_charge_item_id,
        v.source_standard_charge_id,
        v.payer_ordinal,
        v.row_ordinal,
        v.source_rate_ordinal,
        v.code_ordinal,
        v.modifier_code_id,
        cast(null as integer) as npi_ordinal,
        cast(null as integer) as provision_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        cast(null as varchar) as structural_section,
        cast(null as integer) as record_ordinal,
        v.rule_id,
        r.rule_name,
        r.severity,
        'standard_charge' as grain,
        r.disposition,
        v.column_name,
        v.raw_value,
        v.diagnostic_type,
        v.message,
        r.disposition = 'exclude_entity' as excludes_from_silver,
        r.cms_citation
    from deduped v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
