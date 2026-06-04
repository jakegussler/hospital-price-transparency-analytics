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
        cast(null as integer) as source_rate_ordinal,
        standard_charges.reported_schema_version,
        standard_charges.reported_schema_family,
        standard_charges.parser_schema_family,
        standard_charges.parser_schema_version,
        standard_charges.schema_version_mismatch,
        pi.payer_ordinal,
        pi.raw_payer_name,
        pi.clean_payer_name,
        pi.raw_plan_name,
        pi.clean_plan_name,
        {{ hpt_title_case_text('pi.raw_plan_name') }} as display_plan_name,
        pi.raw_methodology,
        pi.clean_methodology,
        pi.standard_charge_dollar as negotiated_dollar,
        pi.standard_charge_percentage as negotiated_percentage,
        pi.standard_charge_algorithm as negotiated_algorithm,
        pi.estimated_amount,
        pi.median_amount,
        pi.tenth_percentile,
        pi.ninetieth_percentile,
        pi.raw_count,
        pi.additional_payer_notes
    from {{ ref('stg_bronze__payers_information') }} pi
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on pi.snapshot_id = standard_charges.snapshot_id
        and pi.standard_charge_id = standard_charges.source_standard_charge_id
    where not exists (
        select 1
        from {{ ref('val__payer_rate_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = pi.snapshot_id
            and r.source_standard_charge_id = pi.standard_charge_id
            and r.payer_ordinal = pi.payer_ordinal
    )
),

csv_rates as (
    with signed_rate_rows as (
        select
            r.*,
            row_items.silver_charge_item_id,
            {{ hpt_surrogate_key([
                'r.snapshot_id',
                'row_items.silver_charge_item_id',
                'r.raw_setting',
                'r.clean_setting',
                'r.raw_billing_class',
                'r.clean_billing_class',
                'r.gross_charge',
                'r.discounted_cash',
                'r.minimum',
                'r.maximum',
                'r.raw_modifiers',
                'r.additional_generic_notes'
            ]) }} as standard_charge_signature
        from {{ ref('stg_bronze__csv_charge_rows') }} r
        inner join {{ ref('slv_base__csv_charge_row_items') }} row_items
            on r.snapshot_id = row_items.snapshot_id
            and r.row_ordinal = row_items.row_ordinal
    )

    select
        {{ hpt_surrogate_key([
            'r.snapshot_id',
            "'csv'",
            'r.row_ordinal',
            'r.source_rate_ordinal'
        ]) }} as silver_payer_rate_id,
        standard_charges.silver_standard_charge_id,
        standard_charges.silver_charge_item_id,
        r.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as source_charge_ordinal,
        r.row_ordinal as source_row_ordinal,
        r.source_rate_ordinal,
        standard_charges.reported_schema_version,
        standard_charges.reported_schema_family,
        standard_charges.parser_schema_family,
        standard_charges.parser_schema_version,
        standard_charges.schema_version_mismatch,
        cast(null as integer) as payer_ordinal,
        r.raw_payer_name,
        r.clean_payer_name,
        r.raw_plan_name,
        r.clean_plan_name,
        {{ hpt_title_case_text('r.raw_plan_name') }} as display_plan_name,
        r.raw_methodology,
        r.clean_methodology,
        r.negotiated_dollar,
        r.negotiated_percentage,
        r.negotiated_algorithm,
        cast(null as decimal(18, 4)) as estimated_amount,
        r.median_amount,
        r.tenth_percentile,
        r.ninetieth_percentile,
        r.raw_count,
        r.additional_payer_notes
    from signed_rate_rows r
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on r.snapshot_id = standard_charges.snapshot_id
        and r.silver_charge_item_id = standard_charges.silver_charge_item_id
        and r.standard_charge_signature = standard_charges.standard_charge_signature
    where not exists (
        select 1
        from {{ ref('val__payer_rate_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
            and rej.source_rate_ordinal = r.source_rate_ordinal
    )
)

select * from json_rates
union all
select * from csv_rates
