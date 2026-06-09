-- Normalize JSON and CSV payer rates to one validation grain, then emit one row
-- per failing payer-rate value.
{% set payer_decimal_columns = [
    ('standard_charge_dollar', 'standard_charge_dollar'),
    ('estimated_amount', 'estimated_amount'),
    ('median_amount', 'median_amount'),
    ('tenth_percentile', '10th_percentile'),
    ('ninetieth_percentile', '90th_percentile')
] %}
{% set payer_double_columns = [
    ('standard_charge_percentage', 'standard_charge_percentage')
] %}

with json_rates as (
    select
        pi.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        sci.parser_schema_family,
        coalesce(sci.parser_schema_family, sci.reported_schema_family) as effective_schema_family,
        sci.charge_item_id as source_charge_item_id,
        pi.standard_charge_id as source_standard_charge_id,
        cast(pi.payer_ordinal as integer) as payer_ordinal,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        pi.payer_name as raw_payer_name,
        {{ hpt_clean_text('pi.payer_name') }} as clean_payer_name,
        pi.plan_name as raw_plan_name,
        {{ hpt_clean_text('pi.plan_name') }} as clean_plan_name,
        pi.methodology as raw_methodology,
        {{ hpt_clean_text('pi.methodology') }} as clean_methodology,
        pi.standard_charge_dollar as raw_standard_charge_dollar,
        pi.standard_charge_percentage as raw_standard_charge_percentage,
        pi.standard_charge_algorithm as raw_standard_charge_algorithm,
        {{ hpt_bronze_column_or_null('payers_information', 'estimated_amount') }} as raw_estimated_amount,
        pi.median_amount as raw_median_amount,
        pi.tenth_percentile as raw_tenth_percentile,
        pi.ninetieth_percentile as raw_ninetieth_percentile,
        pi.count as raw_count,
        pi.additional_payer_notes,
        sc.additional_generic_notes
    from {{ source('bronze', 'payers_information') }} pi
    inner join {{ source('bronze', 'standard_charges') }} sc
        on pi.snapshot_id = sc.snapshot_id
        and pi.standard_charge_id = sc.standard_charge_id
    inner join {{ ref('stg_bronze__standard_charge_info') }} sci
        on sc.snapshot_id = sci.snapshot_id
        and sc.charge_item_id = sci.charge_item_id
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on pi.snapshot_id = hs.snapshot_id
    where 1 = 1
        {{ hpt_snapshot_filter('pi') }}
),

csv_raw as (
    select
        b.snapshot_id,
        hs.hospital_id,
        {{ hpt_clean_text('b.source_format') }} as source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        '3.0' as parser_schema_family,
        '3.0' as effective_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        cast(b.row_ordinal as integer) as row_ordinal,
        b.payer_name as raw_payer_name,
        {{ hpt_clean_text('b.payer_name') }} as clean_payer_name,
        b.plan_name as raw_plan_name,
        {{ hpt_clean_text('b.plan_name') }} as clean_plan_name,
        b.methodology as raw_methodology,
        {{ hpt_clean_text('b.methodology') }} as clean_methodology,
        b.standard_charge_negotiated_dollar as raw_standard_charge_dollar,
        b.standard_charge_negotiated_percentage as raw_standard_charge_percentage,
        b.standard_charge_negotiated_algorithm as raw_standard_charge_algorithm,
        cast(null as varchar) as raw_estimated_amount,
        b.median_amount as raw_median_amount,
        b.tenth_percentile as raw_tenth_percentile,
        b.ninetieth_percentile as raw_ninetieth_percentile,
        b.count as raw_count,
        b.additional_payer_notes,
        b.additional_generic_notes
    from {{ source('bronze', 'csv_charge_rows') }} b
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on b.snapshot_id = hs.snapshot_id
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on b.snapshot_id = mr.snapshot_id
        and cast(b.row_ordinal as integer) = mr.row_ordinal
        and not mr.is_standalone_modifier
    where 1 = 1
        {{ hpt_snapshot_filter('b') }}
),

csv_rates as (
    -- CSV has no source rate ordinal, so derive a deterministic key for rejection joins.
    select
        *,
        cast(
            row_number() over (
                partition by snapshot_id, row_ordinal
                order by
                    coalesce(clean_payer_name, ''),
                    coalesce(clean_plan_name, ''),
                    coalesce(cast({{ hpt_safe_decimal('raw_standard_charge_dollar') }} as varchar), ''),
                    coalesce(cast({{ hpt_safe_double('raw_standard_charge_percentage') }} as varchar), ''),
                    coalesce(raw_standard_charge_algorithm, ''),
                    coalesce(clean_methodology, ''),
                    coalesce(additional_payer_notes, '')
            ) - 1
            as integer
        ) as source_rate_ordinal
    from csv_raw
),

rates as (
    select * from json_rates
    union all
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        parser_schema_family,
        effective_schema_family,
        source_charge_item_id,
        source_standard_charge_id,
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        raw_payer_name,
        clean_payer_name,
        raw_plan_name,
        clean_plan_name,
        raw_methodology,
        clean_methodology,
        raw_standard_charge_dollar,
        raw_standard_charge_percentage,
        raw_standard_charge_algorithm,
        raw_estimated_amount,
        raw_median_amount,
        raw_tenth_percentile,
        raw_ninetieth_percentile,
        raw_count,
        additional_payer_notes,
        additional_generic_notes
    from csv_rates
),

rate_flags as (
    -- Centralize presence checks used by the conditional payer-rate rules below.
    select
        *,
        {{ hpt_clean_display_text('raw_standard_charge_dollar') }} is not null as has_dollar,
        {{ hpt_clean_display_text('raw_standard_charge_percentage') }} is not null as has_percentage,
        {{ hpt_clean_display_text('raw_standard_charge_algorithm') }} is not null as has_algorithm,
        {{ hpt_clean_display_text('raw_estimated_amount') }} is not null as has_estimated_amount,
        {{ hpt_clean_display_text('raw_median_amount') }} is not null as has_median_amount,
        {{ hpt_clean_display_text('raw_tenth_percentile') }} is not null as has_tenth_percentile,
        {{ hpt_clean_display_text('raw_ninetieth_percentile') }} is not null as has_ninetieth_percentile,
        {{ hpt_clean_display_text('additional_payer_notes') }} is not null as has_payer_notes,
        {{ hpt_clean_display_text('additional_generic_notes') }} is not null as has_generic_notes,
        {{ hpt_clean_display_text('raw_count') }} as clean_count
    from rates
),

violations as (
    -- Numeric parseability and positivity rules.
    {% for raw_column, public_name in payer_decimal_columns %}
    select
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
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'payer_numeric_parseable' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_cast_failed' as diagnostic_type,
        '{{ public_name }} is non-empty but cannot be cast to decimal(18,4).' as message
    from rate_flags
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
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        cast(null as integer),
        cast(null as varchar),
        'payer_numeric_positive' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_not_positive' as diagnostic_type,
        '{{ public_name }} must be greater than zero.' as message
    from rate_flags
    where {{ hpt_safe_decimal('raw_' ~ raw_column) }} is not null
        and {{ hpt_safe_decimal('raw_' ~ raw_column) }} <= 0

    union all
    {% endfor %}

    {% for raw_column, public_name in payer_double_columns %}
    select
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
        cast(null as integer),
        cast(null as varchar),
        'payer_numeric_parseable' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_cast_failed' as diagnostic_type,
        '{{ public_name }} is non-empty but cannot be cast to double.' as message
    from rate_flags
    where {{ hpt_clean_display_text('raw_' ~ raw_column) }} is not null
        and {{ hpt_safe_double('raw_' ~ raw_column) }} is null

    union all

    select
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
        cast(null as integer),
        cast(null as varchar),
        'payer_numeric_positive' as rule_id,
        '{{ public_name }}' as column_name,
        raw_{{ raw_column }} as raw_value,
        'numeric_not_positive' as diagnostic_type,
        '{{ public_name }} must be greater than zero.' as message
    from rate_flags
    where {{ hpt_safe_double('raw_' ~ raw_column) }} is not null
        and {{ hpt_safe_double('raw_' ~ raw_column) }} <= 0

    union all
    {% endfor %}

    -- Payer identity, negotiated-charge, and methodology rules.
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'payer_required_identity_and_methodology',
        case
            when clean_payer_name is null then 'payer_name'
            when clean_plan_name is null then 'plan_name'
            else 'methodology'
        end,
        concat(
            'payer=', coalesce(raw_payer_name, '<null>'),
            '; plan=', coalesce(raw_plan_name, '<null>'),
            '; methodology=', coalesce(raw_methodology, '<null>')
        ),
        'required_field_missing',
        'Payer rate rows require payer name, plan name, and methodology.'
    from rate_flags
    where source_format_family = 'json'
        and (
            clean_payer_name is null
            or clean_plan_name is null
            or clean_methodology is null
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'csv_payer_identity_required_with_rate',
        case
            when clean_payer_name is null then 'payer_name'
            when clean_plan_name is null then 'plan_name'
            else 'methodology'
        end,
        concat(
            'payer=', coalesce(raw_payer_name, '<null>'),
            '; plan=', coalesce(raw_plan_name, '<null>'),
            '; methodology=', coalesce(raw_methodology, '<null>')
        ),
        'required_field_missing',
        'CSV payer-specific rate data requires payer name, plan name, and methodology.'
    from rate_flags
    where source_format_family = 'csv'
        and (has_dollar or has_percentage or has_algorithm)
        and (clean_payer_name is null or clean_plan_name is null or clean_methodology is null)

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'csv_payer_rate_required_with_identity', 'standard_charge',
        concat(
            'payer=', coalesce(raw_payer_name, '<null>'),
            '; plan=', coalesce(raw_plan_name, '<null>'),
            '; dollar=', coalesce(raw_standard_charge_dollar, '<null>'),
            '; percentage=', coalesce(raw_standard_charge_percentage, '<null>'),
            '; algorithm=', coalesce(raw_standard_charge_algorithm, '<null>')
        ),
        'conditional_required_value_missing',
        'CSV payer or plan identity is encoded without any payer-specific negotiated charge value.'
    from rate_flags
    where source_format_family = 'csv'
        and (clean_payer_name is not null or clean_plan_name is not null)
        and not has_dollar
        and not has_percentage
        and not has_algorithm

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'methodology_allowed_values', 'methodology', raw_methodology,
        'accepted_value_invalid',
        'Methodology is outside the CMS contract methodology value set.'
    from rate_flags
    where clean_methodology is not null
        and clean_methodology not in (
            'case rate',
            'fee schedule',
            'percent of total billed charges',
            'per diem',
            'other'
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'payer_requires_negotiated_charge', 'standard_charge',
        concat(
            'dollar=', coalesce(raw_standard_charge_dollar, '<null>'),
            '; percentage=', coalesce(raw_standard_charge_percentage, '<null>'),
            '; algorithm=', coalesce(raw_standard_charge_algorithm, '<null>')
        ),
        'conditional_required_value_missing',
        'Payer row lacks dollar, percentage, and algorithm negotiated charge values.'
    from rate_flags
    where source_format_family = 'json'
        and not has_dollar
        and not has_percentage
        and not has_algorithm

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'methodology_other_requires_notes', 'additional_notes',
        concat(
            'methodology=', coalesce(raw_methodology, '<null>'),
            '; payer_notes=', coalesce(additional_payer_notes, '<null>'),
            '; generic_notes=', coalesce(additional_generic_notes, '<null>')
        ),
        'conditional_required_field_missing',
        'Other methodology requires payer or generic explanatory notes.'
    from rate_flags
    where clean_methodology = 'other'
        and not has_payer_notes
        and not has_generic_notes

    union all

    -- Prefer the accepted parser shape when it disagrees with the reported
    -- header so schema-family conditionals match the record that reached Bronze.
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'v2_2_percentage_or_algorithm_requires_estimated_amount',
        'estimated_amount',
        raw_estimated_amount,
        'conditional_required_field_missing',
        'Schema family 2.2 percentage or algorithm rates without dollar amount require estimated_amount.'
    from rate_flags
    where source_format_family = 'json'
        and effective_schema_family = '2.2'
        and (has_percentage or has_algorithm)
        and not has_dollar
        and not has_estimated_amount

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'v3_percentage_or_algorithm_requires_count', 'count', raw_count,
        'conditional_required_field_missing',
        'Schema family 3.0 percentage or algorithm rates require count.'
    from rate_flags
    where effective_schema_family = '3.0'
        and (has_percentage or has_algorithm)
        and clean_count is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'v3_count_allowed_format', 'count', raw_count,
        'count_format_invalid',
        'Count must be 0, 1 through 10, or a whole number 11 or greater without thousands separators.'
    from rate_flags
    where effective_schema_family = '3.0'
        and clean_count is not null
        and not (
            clean_count = '0'
            or clean_count = '1 through 10'
            or regexp_matches(clean_count, '^(1[1-9]|[2-9][0-9]+|[1-9][0-9]{2,})$')
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'v3_count_nonzero_requires_allowed_amounts',
        'allowed_amounts',
        concat(
            'count=', coalesce(raw_count, '<null>'),
            '; median=', coalesce(raw_median_amount, '<null>'),
            '; 10th=', coalesce(raw_tenth_percentile, '<null>'),
            '; 90th=', coalesce(raw_ninetieth_percentile, '<null>')
        ),
        'conditional_required_field_missing',
        'Schema family 3.0 nonzero-count percentage or algorithm rates require median, 10th, and 90th percentile amounts.'
    from rate_flags
    where effective_schema_family = '3.0'
        and (has_percentage or has_algorithm)
        and clean_count is not null
        and clean_count != '0'
        and (not has_median_amount or not has_tenth_percentile or not has_ninetieth_percentile)

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer), cast(null as varchar),
        'count_zero_requires_explanation',
        'additional_notes',
        concat(
            'count=', coalesce(raw_count, '<null>'),
            '; payer_notes=', coalesce(additional_payer_notes, '<null>'),
            '; generic_notes=', coalesce(additional_generic_notes, '<null>')
        ),
        'conditional_required_field_missing',
        'Count zero for percentage or algorithm rates requires payer or generic explanatory notes.'
    from rate_flags
    where effective_schema_family = '3.0'
        and (has_percentage or has_algorithm)
        and clean_count = '0'
        and not has_payer_notes
        and not has_generic_notes
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'payer_rate'", 'v.rule_id', 'v.column_name',
            'v.source_standard_charge_id', 'v.payer_ordinal', 'v.row_ordinal',
            'v.source_rate_ordinal', 'v.raw_value'
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
        'payer_rate' as grain,
        r.disposition,
        v.column_name,
        v.raw_value,
        v.diagnostic_type,
        v.message,
        r.disposition = 'exclude_entity' as excludes_from_silver,
        r.cms_citation
    from violations v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
