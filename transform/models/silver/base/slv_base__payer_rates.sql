with json_rates as (
    select
        {{ hpt_surrogate_key([
            'standard_charges.snapshot_id',
            "'json'",
            'standard_charges.source_standard_charge_id',
            'pi.payer_ordinal'
        ]) }} as silver_payer_rate_id,
        standard_charges.silver_standard_charge_id,
        standard_charges.silver_charge_item_id,
        standard_charges.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        standard_charges.source_standard_charge_id,
        standard_charges.source_charge_ordinal,
        cast(null as integer) as source_row_ordinal,
        pi.payer_ordinal,
        pi.raw_payer_name,
        pi.clean_payer_name,
        pi.raw_plan_name,
        pi.clean_plan_name,
        pi.raw_methodology,
        pi.clean_methodology,
        pi.standard_charge_dollar as negotiated_dollar,
        pi.standard_charge_percentage as negotiated_percentage,
        pi.standard_charge_algorithm as negotiated_algorithm,
        pi.median_amount,
        pi.tenth_percentile,
        pi.ninetieth_percentile,
        pi.raw_count,
        pi.additional_payer_notes
    from {{ ref('stg_bronze__payers_information') }} pi
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on pi.snapshot_id = standard_charges.snapshot_id
        and pi.standard_charge_id = standard_charges.source_standard_charge_id
),

csv_rates as (
    select
        {{ hpt_surrogate_key(['r.snapshot_id', "'csv'", 'r.row_ordinal']) }} as silver_payer_rate_id,
        standard_charges.silver_standard_charge_id,
        standard_charges.silver_charge_item_id,
        r.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as source_charge_ordinal,
        r.row_ordinal as source_row_ordinal,
        cast(null as integer) as payer_ordinal,
        r.raw_payer_name,
        r.clean_payer_name,
        r.raw_plan_name,
        r.clean_plan_name,
        r.raw_methodology,
        r.clean_methodology,
        r.negotiated_dollar,
        r.negotiated_percentage,
        r.negotiated_algorithm,
        r.median_amount,
        r.tenth_percentile,
        r.ninetieth_percentile,
        r.raw_count,
        r.additional_payer_notes
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on r.snapshot_id = standard_charges.snapshot_id
        and r.row_ordinal = standard_charges.source_row_ordinal
)

select * from json_rates
union all
select * from csv_rates
