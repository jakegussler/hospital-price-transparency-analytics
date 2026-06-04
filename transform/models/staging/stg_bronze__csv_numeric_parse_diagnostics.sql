-- Queryable diagnostics for malformed numeric values in CSV Bronze.
--
-- CSV Bronze stores numeric-looking cells as raw text (ADR 0010); dbt staging
-- casts them with hpt_safe_decimal / hpt_safe_double. This model emits one row
-- per non-empty raw value that fails the same cast staging applies, so bad
-- numbers are reviewable instead of silently becoming null.
--
-- For each candidate column we flag a value when its display-cleaned form is
-- non-null (i.e. not blank / 'null' / 'N/A') but the safe cast returns null.
-- Item-level columns (gross/min/max/discounted_cash/drug_unit) repeat across
-- payer groups after CSV Wide unpivoting, so they carry no payer/plan and are
-- deduped per (snapshot_id, row_ordinal, column_name); payer-level columns
-- carry payer/plan so distinct payers stay distinct.

{% set decimal_item_columns = [
    'standard_charge_gross',
    'standard_charge_discounted_cash',
    'standard_charge_min',
    'standard_charge_max',
] %}

{% set double_item_columns = [
    'drug_unit_of_measurement',
] %}

{% set decimal_payer_columns = [
    'standard_charge_negotiated_dollar',
    'median_amount',
    'tenth_percentile',
    'ninetieth_percentile',
] %}

{% set double_payer_columns = [
    'standard_charge_negotiated_percentage',
] %}

with source_rows as (
    select
        snapshot_id,
        cast(row_ordinal as integer) as row_ordinal,
        {{ hpt_clean_text('source_format') }} as source_format,
        {{ hpt_clean_text('payer_name') }} as payer_name,
        {{ hpt_clean_text('plan_name') }} as plan_name,
        drug_unit_of_measurement,
        standard_charge_gross,
        standard_charge_discounted_cash,
        standard_charge_min,
        standard_charge_max,
        standard_charge_negotiated_dollar,
        standard_charge_negotiated_percentage,
        median_amount,
        tenth_percentile,
        ninetieth_percentile
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
),

flagged as (
    {% set diagnostic_blocks = [] %}

    {%- for column_name in decimal_item_columns %}
    select
        snapshot_id,
        row_ordinal,
        source_format,
        cast(null as varchar) as payer_name,
        cast(null as varchar) as plan_name,
        '{{ column_name }}' as column_name,
        {{ hpt_clean_display_text(column_name) }} as raw_value,
        'decimal(18,4)' as target_type,
        'numeric_cast_failed' as diagnostic_type
    from source_rows
    where {{ hpt_clean_display_text(column_name) }} is not null
        and {{ hpt_safe_decimal(column_name) }} is null

    union all
    {% endfor -%}

    {%- for column_name in double_item_columns %}
    select
        snapshot_id,
        row_ordinal,
        source_format,
        cast(null as varchar) as payer_name,
        cast(null as varchar) as plan_name,
        '{{ column_name }}' as column_name,
        {{ hpt_clean_display_text(column_name) }} as raw_value,
        'double' as target_type,
        'numeric_cast_failed' as diagnostic_type
    from source_rows
    where {{ hpt_clean_display_text(column_name) }} is not null
        and {{ hpt_safe_double(column_name) }} is null

    union all
    {% endfor -%}

    {%- for column_name in decimal_payer_columns %}
    select
        snapshot_id,
        row_ordinal,
        source_format,
        payer_name,
        plan_name,
        '{{ column_name }}' as column_name,
        {{ hpt_clean_display_text(column_name) }} as raw_value,
        'decimal(18,4)' as target_type,
        'numeric_cast_failed' as diagnostic_type
    from source_rows
    where {{ hpt_clean_display_text(column_name) }} is not null
        and {{ hpt_safe_decimal(column_name) }} is null

    union all
    {% endfor -%}

    {%- for column_name in double_payer_columns %}
    select
        snapshot_id,
        row_ordinal,
        source_format,
        payer_name,
        plan_name,
        '{{ column_name }}' as column_name,
        {{ hpt_clean_display_text(column_name) }} as raw_value,
        'double' as target_type,
        'numeric_cast_failed' as diagnostic_type
    from source_rows
    where {{ hpt_clean_display_text(column_name) }} is not null
        and {{ hpt_safe_double(column_name) }} is null

    {% if not loop.last %}union all{% endif %}
    {% endfor -%}
)

select
    snapshot_id,
    row_ordinal,
    source_format,
    payer_name,
    plan_name,
    column_name,
    raw_value,
    target_type,
    diagnostic_type
from flagged
qualify row_number() over (
    partition by
        snapshot_id,
        row_ordinal,
        column_name,
        raw_value,
        source_format,
        coalesce(payer_name, ''),
        coalesce(plan_name, '')
    order by 1
) = 1
