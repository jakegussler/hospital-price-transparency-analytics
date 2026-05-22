with json_standard_charges as (
    select
        {{ hpt_surrogate_key([
            'sc.snapshot_id',
            "'json'",
            'sc.standard_charge_id'
        ]) }} as silver_standard_charge_id,
        ci.silver_charge_item_id,
        sc.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        sc.standard_charge_id as source_standard_charge_id,
        sc.charge_ordinal as source_charge_ordinal,
        cast(null as integer) as source_row_ordinal,
        sc.raw_setting,
        sc.clean_setting,
        sc.raw_billing_class,
        sc.clean_billing_class,
        sc.gross_charge,
        sc.discounted_cash,
        sc.minimum,
        sc.maximum,
        sc.additional_generic_notes
    from {{ ref('stg_bronze__standard_charges') }} sc
    inner join {{ ref('slv_base__charge_items') }} ci
        on sc.snapshot_id = ci.snapshot_id
        and sc.charge_item_id = ci.source_charge_item_id
),

csv_standard_charges as (
    select
        {{ hpt_surrogate_key([
            'r.snapshot_id',
            "'csv'",
            'r.row_ordinal'
        ]) }} as silver_standard_charge_id,
        row_items.silver_charge_item_id,
        r.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as source_charge_ordinal,
        r.row_ordinal as source_row_ordinal,
        r.raw_setting,
        r.clean_setting,
        r.raw_billing_class,
        r.clean_billing_class,
        r.gross_charge,
        r.discounted_cash,
        r.minimum,
        r.maximum,
        r.additional_generic_notes
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('slv_base__csv_charge_row_items') }} row_items
        on r.snapshot_id = row_items.snapshot_id
        and r.row_ordinal = row_items.row_ordinal
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
)

select * from json_standard_charges
union all
select * from csv_standard_charges
