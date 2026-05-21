with json_rates as (
    select
        {{ hpt_surrogate_key([
            'sc.snapshot_id',
            "'json'",
            'sc.standard_charge_id',
            'pi.payer_ordinal'
        ]) }} as silver_payer_rate_id,
        ci.silver_charge_item_id,
        sc.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        sc.standard_charge_id as source_standard_charge_id,
        sc.charge_ordinal as source_charge_ordinal,
        cast(null as integer) as source_row_ordinal,
        pi.payer_ordinal,
        case
            when pi.standard_charge_id is null then 'generic_standard_charge'
            else 'payer_specific_rate'
        end as rate_record_type,
        pi.raw_payer_name,
        pi.clean_payer_name,
        pi.raw_plan_name,
        pi.clean_plan_name,
        sc.raw_setting,
        sc.clean_setting,
        sc.raw_billing_class,
        sc.clean_billing_class,
        pi.raw_methodology,
        pi.clean_methodology,
        sc.gross_charge,
        sc.discounted_cash,
        sc.minimum,
        sc.maximum,
        pi.standard_charge_dollar as negotiated_dollar,
        pi.standard_charge_percentage as negotiated_percentage,
        pi.standard_charge_algorithm as negotiated_algorithm,
        pi.median_amount,
        pi.tenth_percentile,
        pi.ninetieth_percentile,
        pi.raw_count,
        sc.additional_generic_notes,
        pi.additional_payer_notes
    from {{ ref('stg_bronze__standard_charges') }} sc
    inner join {{ ref('slv_base__charge_items') }} ci
        on sc.snapshot_id = ci.snapshot_id
        and sc.charge_item_id = ci.source_charge_item_id
    left join {{ ref('stg_bronze__payers_information') }} pi
        on sc.snapshot_id = pi.snapshot_id
        and sc.standard_charge_id = pi.standard_charge_id
),

csv_rates as (
    select
        {{ hpt_surrogate_key(['r.snapshot_id', "'csv'", 'r.row_ordinal']) }} as silver_payer_rate_id,
        row_items.silver_charge_item_id,
        r.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as source_charge_ordinal,
        r.row_ordinal as source_row_ordinal,
        cast(null as integer) as payer_ordinal,
        'csv_charge_row' as rate_record_type,
        r.raw_payer_name,
        r.clean_payer_name,
        r.raw_plan_name,
        r.clean_plan_name,
        r.raw_setting,
        r.clean_setting,
        r.raw_billing_class,
        r.clean_billing_class,
        r.raw_methodology,
        r.clean_methodology,
        r.gross_charge,
        r.discounted_cash,
        r.minimum,
        r.maximum,
        r.negotiated_dollar,
        r.negotiated_percentage,
        r.negotiated_algorithm,
        r.median_amount,
        r.tenth_percentile,
        r.ninetieth_percentile,
        r.raw_count,
        r.additional_generic_notes,
        r.additional_payer_notes
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('slv_base__csv_charge_row_items') }} row_items
        on r.snapshot_id = row_items.snapshot_id
        and r.row_ordinal = row_items.row_ordinal
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
)

select * from json_rates
union all
select * from csv_rates
