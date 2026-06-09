with staged as (
    select
        snapshot_id,
        cast(row_ordinal as integer) as row_ordinal,
        description as raw_description,
        {{ hpt_normalize_text('description') }} as clean_description,
        setting as raw_setting,
        {{ hpt_normalize_text('setting') }} as clean_setting,
        billing_class as raw_billing_class,
        {{ hpt_normalize_text('billing_class') }} as clean_billing_class,
        {{ hpt_safe_double('drug_unit_of_measurement') }} as drug_unit,
        drug_type_of_measurement as raw_drug_unit_type,
        {{ hpt_normalize_text('drug_type_of_measurement') }} as clean_drug_unit_type,
        {{ hpt_safe_decimal('standard_charge_gross') }} as gross_charge,
        {{ hpt_safe_decimal('standard_charge_discounted_cash') }} as discounted_cash,
        {{ hpt_safe_decimal('standard_charge_min') }} as minimum,
        {{ hpt_safe_decimal('standard_charge_max') }} as maximum,
        modifiers as raw_modifiers,
        payer_name as raw_payer_name,
        {{ hpt_nullify_sentinel_text('payer_name') }} as clean_payer_name,
        plan_name as raw_plan_name,
        {{ hpt_nullify_sentinel_text('plan_name') }} as clean_plan_name,
        {{ hpt_safe_decimal('standard_charge_negotiated_dollar') }} as negotiated_dollar,
        {{ hpt_safe_double('standard_charge_negotiated_percentage') }} as negotiated_percentage,
        standard_charge_negotiated_algorithm as negotiated_algorithm,
        methodology as raw_methodology,
        {{ hpt_nullify_sentinel_text('methodology') }} as clean_methodology,
        {{ hpt_safe_decimal('median_amount') }} as median_amount,
        {{ hpt_safe_decimal('tenth_percentile') }} as tenth_percentile,
        {{ hpt_safe_decimal('ninetieth_percentile') }} as ninetieth_percentile,
        count as raw_count,
        additional_generic_notes,
        additional_payer_notes,
        {{ hpt_normalize_text('source_format') }} as source_format,
        columns('^code_[0-9]+(_type)?$')
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)

select
    *,
    cast(
        row_number() over (
            partition by snapshot_id, row_ordinal
            order by
                coalesce(clean_payer_name, ''),
                coalesce(clean_plan_name, ''),
                coalesce(cast(negotiated_dollar as varchar), ''),
                coalesce(cast(negotiated_percentage as varchar), ''),
                coalesce(negotiated_algorithm, ''),
                coalesce(clean_methodology, ''),
                coalesce(additional_payer_notes, '')
        ) - 1
        as integer
    ) as source_rate_ordinal
from staged
