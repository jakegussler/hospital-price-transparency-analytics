select
    snapshot_id,
    standard_charge_id,
    cast(payer_ordinal as integer) as payer_ordinal,
    payer_name as raw_payer_name,
    {{ hpt_clean_text('payer_name') }} as clean_payer_name,
    plan_name as raw_plan_name,
    {{ hpt_clean_text('plan_name') }} as clean_plan_name,
    methodology as raw_methodology,
    {{ hpt_clean_text('methodology') }} as clean_methodology,
    {{ hpt_safe_decimal('standard_charge_dollar') }} as standard_charge_dollar,
    {{ hpt_safe_double('standard_charge_percentage') }} as standard_charge_percentage,
    standard_charge_algorithm,
    {{ hpt_safe_decimal(
        hpt_bronze_column_or_null('payers_information', 'estimated_amount', 'double')
    ) }} as estimated_amount,
    {{ hpt_safe_decimal('median_amount') }} as median_amount,
    {{ hpt_safe_decimal('tenth_percentile') }} as tenth_percentile,
    {{ hpt_safe_decimal('ninetieth_percentile') }} as ninetieth_percentile,
    count as raw_count,
    additional_payer_notes
from {{ hpt_staging_source(source('bronze', 'payers_information'), rows=1000000) }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
