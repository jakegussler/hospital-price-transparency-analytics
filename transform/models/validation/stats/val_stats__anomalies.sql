with json_rate_context as (
    select
        pi.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        sci.reported_schema_family,
        sc.standard_charge_id as source_standard_charge_id,
        cast(pi.payer_ordinal as integer) as payer_ordinal,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        {{ hpt_safe_decimal('sc.gross_charge') }} as gross_charge,
        {{ hpt_safe_decimal('sc.minimum') }} as minimum,
        {{ hpt_safe_decimal('sc.maximum') }} as maximum,
        {{ hpt_safe_decimal('pi.standard_charge_dollar') }} as negotiated_dollar,
        {{ hpt_safe_double('pi.standard_charge_percentage') }} as negotiated_percentage,
        {{ hpt_safe_decimal(hpt_bronze_column_or_null('payers_information', 'estimated_amount')) }} as estimated_amount
    from {{ source('bronze', 'payers_information') }} pi
    inner join {{ source('bronze', 'standard_charges') }} sc
        on pi.snapshot_id = sc.snapshot_id
        and pi.standard_charge_id = sc.standard_charge_id
    inner join {{ ref('stg_bronze__standard_charge_info') }} sci
        on sc.snapshot_id = sci.snapshot_id
        and sc.charge_item_id = sci.charge_item_id
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on pi.snapshot_id = hs.snapshot_id
    where 1 = 1 {{ hpt_snapshot_filter('pi') }}
),

csv_rate_context as (
    select
        b.snapshot_id,
        hs.hospital_id,
        {{ hpt_clean_text('b.source_format') }} as source_format,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        cast(b.row_ordinal as integer) as row_ordinal,
        cast(
            row_number() over (
                partition by b.snapshot_id, cast(b.row_ordinal as integer)
                order by
                    coalesce({{ hpt_clean_text('b.payer_name') }}, ''),
                    coalesce({{ hpt_clean_text('b.plan_name') }}, ''),
                    coalesce(cast({{ hpt_safe_decimal('b.standard_charge_negotiated_dollar') }} as varchar), ''),
                    coalesce(cast({{ hpt_safe_double('b.standard_charge_negotiated_percentage') }} as varchar), ''),
                    coalesce(b.standard_charge_negotiated_algorithm, ''),
                    coalesce({{ hpt_clean_text('b.methodology') }}, ''),
                    coalesce(b.additional_payer_notes, '')
            ) - 1 as integer
        ) as source_rate_ordinal,
        {{ hpt_safe_decimal('b.standard_charge_gross') }} as gross_charge,
        {{ hpt_safe_decimal('b.standard_charge_min') }} as minimum,
        {{ hpt_safe_decimal('b.standard_charge_max') }} as maximum,
        {{ hpt_safe_decimal('b.standard_charge_negotiated_dollar') }} as negotiated_dollar,
        {{ hpt_safe_double('b.standard_charge_negotiated_percentage') }} as negotiated_percentage,
        cast(null as decimal(18, 4)) as estimated_amount
    from {{ source('bronze', 'csv_charge_rows') }} b
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on b.snapshot_id = hs.snapshot_id
    where 1 = 1 {{ hpt_snapshot_filter('b') }}
),

rate_context as (
    select * from json_rate_context
    union all
    select * from csv_rate_context
),

anomalies as (
    select
        snapshot_id,
        hospital_id,
        source_format,
        reported_schema_family,
        source_standard_charge_id,
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        'negotiated_dollar_gt_gross_charge' as anomaly_type,
        concat('negotiated_dollar=', negotiated_dollar, '; gross_charge=', gross_charge) as details
    from rate_context
    where negotiated_dollar is not null
        and gross_charge is not null
        and negotiated_dollar > gross_charge

    union all

    select
        snapshot_id,
        hospital_id,
        source_format,
        reported_schema_family,
        source_standard_charge_id,
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        'percentage_gt_100' as anomaly_type,
        concat('negotiated_percentage=', negotiated_percentage) as details
    from rate_context
    where negotiated_percentage > 100

    union all

    select
        snapshot_id,
        hospital_id,
        source_format,
        reported_schema_family,
        source_standard_charge_id,
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        'minimum_gt_maximum' as anomaly_type,
        concat('minimum=', minimum, '; maximum=', maximum) as details
    from rate_context
    where minimum is not null
        and maximum is not null
        and minimum > maximum

    union all

    select
        snapshot_id,
        hospital_id,
        source_format,
        reported_schema_family,
        source_standard_charge_id,
        payer_ordinal,
        row_ordinal,
        source_rate_ordinal,
        'estimated_amount_present_without_percentage_or_algorithm' as anomaly_type,
        concat('estimated_amount=', estimated_amount) as details
    from rate_context
    where estimated_amount is not null
        and negotiated_percentage is null
)

select
    *,
    'warn' as severity
from anomalies
