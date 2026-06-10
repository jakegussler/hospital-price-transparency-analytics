-- Normalize JSON and CSV standard charges to one grain, then emit value and
-- conditional-rule violations for each charge context.
{% set standard_charge_numeric_columns = [
    ('gross_charge', 'gross_charge'),
    ('discounted_cash', 'discounted_cash'),
    ('minimum', 'minimum'),
    ('maximum', 'maximum')
] %}

with json_payer_rollup as (
    -- Parent standard-charge rules need to know whether any child payer rate
    -- supplies a negotiated value.
    select
        pi.snapshot_id,
        pi.standard_charge_id,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_dollar') }} is not null) as has_payer_dollar,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_percentage') }} is not null) as has_payer_percentage,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_algorithm') }} is not null) as has_payer_algorithm
    from {{ hpt_scoped_source('bronze', 'payers_information') }} pi
    group by pi.snapshot_id, pi.standard_charge_id
),

json_charges as (
    select
        sc.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        sci.parser_schema_family,
        coalesce(sci.parser_schema_family, sci.reported_schema_family) as effective_schema_family,
        sci.charge_item_id as source_charge_item_id,
        sc.standard_charge_id as source_standard_charge_id,
        cast(null as integer) as row_ordinal,
        sc.gross_charge as raw_gross_charge,
        sc.discounted_cash as raw_discounted_cash,
        sc.minimum as raw_minimum,
        sc.maximum as raw_maximum,
        sc.setting as raw_setting,
        {{ hpt_clean_text('sc.setting') }} as clean_setting,
        sc.billing_class as raw_billing_class,
        {{ hpt_clean_text('sc.billing_class') }} as clean_billing_class,
        coalesce(pr.has_payer_dollar, false) as has_payer_dollar,
        coalesce(pr.has_payer_percentage, false) as has_payer_percentage,
        coalesce(pr.has_payer_algorithm, false) as has_payer_algorithm
    from {{ hpt_scoped_source('bronze', 'standard_charges') }} sc
    inner join {{ hpt_scoped_ref('stg_bronze__standard_charge_info') }} sci
        on sc.snapshot_id = sci.snapshot_id
        and sc.charge_item_id = sci.charge_item_id
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on sc.snapshot_id = hs.snapshot_id
    left join json_payer_rollup pr
        on sc.snapshot_id = pr.snapshot_id
        and sc.standard_charge_id = pr.standard_charge_id
),

csv_charges as (
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        '3.0' as parser_schema_family,
        '3.0' as effective_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        r.row_ordinal,
        b.standard_charge_gross as raw_gross_charge,
        b.standard_charge_discounted_cash as raw_discounted_cash,
        b.standard_charge_min as raw_minimum,
        b.standard_charge_max as raw_maximum,
        b.setting as raw_setting,
        r.clean_setting,
        b.billing_class as raw_billing_class,
        r.clean_billing_class,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_dollar') }} is not null as has_payer_dollar,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_percentage') }} is not null as has_payer_percentage,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_algorithm') }} is not null as has_payer_algorithm
    from {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ hpt_scoped_source('bronze', 'csv_charge_rows') }} b
        on r.snapshot_id = b.snapshot_id
        and r.row_ordinal = cast(b.row_ordinal as integer)
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
),

charges as (
    select * from json_charges
    union all
    select * from csv_charges
),

violations as (
    -- Numeric parseability and positivity rules.
    {% for raw_column, public_name in standard_charge_numeric_columns %}
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        source_charge_item_id,
        source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'standard_charge_numeric_parseable' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_cast_failed' as diagnostic_type,
        '{{ public_name }} is non-empty but cannot be cast to decimal(18,4).' as message
    from charges
    where {{ hpt_clean_display_text('raw_' ~ raw_column) }} is not null
        and {{ hpt_safe_decimal('raw_' ~ raw_column) }} is null

    union all

    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        source_charge_item_id,
        source_standard_charge_id,
        cast(null as integer),
        row_ordinal,
        cast(null as integer),
        cast(null as integer),
        cast(null as varchar),
        'standard_charge_numeric_positive' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_not_positive' as diagnostic_type,
        '{{ public_name }} must be greater than zero.' as message
    from charges
    where {{ hpt_safe_decimal('raw_' ~ raw_column) }} is not null
        and {{ hpt_safe_decimal('raw_' ~ raw_column) }} <= 0

    {% if not loop.last %}union all{% endif %}
    {% endfor %}

    union all

    -- Required shape and accepted-value rules.
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'standard_charge_required_setting_shape', 'setting', raw_setting,
        'required_field_missing',
        'Standard charge setting is required.'
    from charges
    where clean_setting is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'setting_allowed_values', 'setting', raw_setting,
        'accepted_value_invalid',
        'Setting must be inpatient, outpatient, or both.'
    from charges
    where clean_setting is not null
        and clean_setting not in ('inpatient', 'outpatient', 'both')

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'billing_class_allowed_values', 'billing_class', raw_billing_class,
        'accepted_value_warn',
        'Billing class is populated outside the documented recommended values.'
    from charges
    where clean_billing_class is not null
        and clean_billing_class not in ('professional', 'facility', 'both')

    union all

    -- Conditional charge-value and payer-dollar rules.
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'charge_requires_any_standard_charge_value', 'standard_charge_values',
        concat(
            'gross=', coalesce(raw_gross_charge, '<null>'),
            '; discounted_cash=', coalesce(raw_discounted_cash, '<null>'),
            '; payer_dollar=', cast(has_payer_dollar as varchar),
            '; payer_percentage=', cast(has_payer_percentage as varchar),
            '; payer_algorithm=', cast(has_payer_algorithm as varchar)
        ),
        'conditional_required_value_missing',
        'A standard charge must have gross, discounted cash, or payer-specific negotiated charge data.'
    from charges
    where {{ hpt_clean_display_text('raw_gross_charge') }} is null
        and {{ hpt_clean_display_text('raw_discounted_cash') }} is null
        and not has_payer_dollar
        and not has_payer_percentage
        and not has_payer_algorithm

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'payer_dollar_requires_minimum_and_maximum',
        case
            when {{ hpt_clean_display_text('raw_minimum') }} is null then 'minimum'
            else 'maximum'
        end,
        concat('minimum=', coalesce(raw_minimum, '<null>'), '; maximum=', coalesce(raw_maximum, '<null>')),
        'conditional_required_field_missing',
        'Payer negotiated dollar charge requires parent minimum and maximum.'
    from charges
    where has_payer_dollar
        and (
            {{ hpt_clean_display_text('raw_minimum') }} is null
            or {{ hpt_clean_display_text('raw_maximum') }} is null
        )
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
