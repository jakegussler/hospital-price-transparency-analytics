-- Profile raw numeric fields across JSON and CSV without excluding malformed
-- values, preserving visibility into both distributions and cast failures.
with numeric_values as (
    -- Normalize source-specific numeric columns to a shared long-form contract.
    select snapshot_id, 'standard_charge' as grain, 'gross_charge' as column_name, gross_charge as raw_value, {{ hpt_safe_decimal('gross_charge') }}::double as numeric_value
    from {{ source('bronze', 'standard_charges') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'discounted_cash', discounted_cash, {{ hpt_safe_decimal('discounted_cash') }}::double
    from {{ source('bronze', 'standard_charges') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'minimum', minimum, {{ hpt_safe_decimal('minimum') }}::double
    from {{ source('bronze', 'standard_charges') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'maximum', maximum, {{ hpt_safe_decimal('maximum') }}::double
    from {{ source('bronze', 'standard_charges') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'standard_charge_dollar', standard_charge_dollar, {{ hpt_safe_decimal('standard_charge_dollar') }}::double
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'standard_charge_percentage', standard_charge_percentage, {{ hpt_safe_double('standard_charge_percentage') }}
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'estimated_amount', {{ hpt_bronze_column_or_null('payers_information', 'estimated_amount') }}, {{ hpt_safe_decimal(hpt_bronze_column_or_null('payers_information', 'estimated_amount')) }}::double
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'median_amount', median_amount, {{ hpt_safe_decimal('median_amount') }}::double
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'tenth_percentile', tenth_percentile, {{ hpt_safe_decimal('tenth_percentile') }}::double
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'ninetieth_percentile', ninetieth_percentile, {{ hpt_safe_decimal('ninetieth_percentile') }}::double
    from {{ source('bronze', 'payers_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'drug', 'unit', unit, {{ hpt_safe_double('unit') }}
    from {{ source('bronze', 'drug_information') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'standard_charge_gross', standard_charge_gross, {{ hpt_safe_decimal('standard_charge_gross') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'standard_charge_discounted_cash', standard_charge_discounted_cash, {{ hpt_safe_decimal('standard_charge_discounted_cash') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'standard_charge_min', standard_charge_min, {{ hpt_safe_decimal('standard_charge_min') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'standard_charge', 'standard_charge_max', standard_charge_max, {{ hpt_safe_decimal('standard_charge_max') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'standard_charge_negotiated_dollar', standard_charge_negotiated_dollar, {{ hpt_safe_decimal('standard_charge_negotiated_dollar') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'standard_charge_negotiated_percentage', standard_charge_negotiated_percentage, {{ hpt_safe_double('standard_charge_negotiated_percentage') }}
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'median_amount', median_amount, {{ hpt_safe_decimal('median_amount') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'tenth_percentile', tenth_percentile, {{ hpt_safe_decimal('tenth_percentile') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'payer_rate', 'ninetieth_percentile', ninetieth_percentile, {{ hpt_safe_decimal('ninetieth_percentile') }}::double
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
    union all
    select snapshot_id, 'drug', 'drug_unit_of_measurement', drug_unit_of_measurement, {{ hpt_safe_double('drug_unit_of_measurement') }}
    from {{ source('bronze', 'csv_charge_rows') }}
    where 1 = 1 {{ hpt_snapshot_filter() }}
),

classified as (
    -- Keep blank values distinct from non-empty values that fail numeric casting.
    select
        snapshot_id,
        grain,
        column_name,
        raw_value,
        numeric_value,
        {{ hpt_trimmed_text('raw_value') }} as clean_raw_value
    from numeric_values
)

select
    snapshot_id,
    grain,
    column_name,
    count(*) as row_count,
    count(*) filter (where clean_raw_value is null) as null_or_blank_count,
    count(*) filter (where clean_raw_value is not null and numeric_value is null) as non_castable_count,
    min(numeric_value) as min_value,
    max(numeric_value) as max_value,
    median(numeric_value) as median_value,
    quantile_cont(numeric_value, 0.10) as p10_value,
    quantile_cont(numeric_value, 0.90) as p90_value,
    count(*) filter (where numeric_value = 0) as zero_count,
    count(*) filter (where numeric_value < 0) as negative_count
from classified
group by
    snapshot_id,
    grain,
    column_name
