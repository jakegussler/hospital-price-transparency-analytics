with json_items as (
    select
        {{ hpt_surrogate_key(['sci.snapshot_id', "'json'", 'sci.charge_item_id']) }} as silver_charge_item_id,
        sci.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        sci.charge_item_id as source_charge_item_id,
        sci.item_ordinal as source_item_ordinal,
        cast(null as integer) as first_source_row_ordinal,
        cast(null as integer) as last_source_row_ordinal,
        1 as source_row_count,
        sci.raw_description,
        sci.clean_description,
        di.drug_unit,
        di.raw_drug_unit_type,
        di.clean_drug_unit_type,
        {{ hpt_surrogate_key(['sci.snapshot_id', "'json'", 'sci.charge_item_id']) }} as charge_item_signature
    from {{ ref('stg_bronze__standard_charge_info') }} sci
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on sci.snapshot_id = hs.snapshot_id
    left join {{ ref('stg_bronze__drug_information') }} di
        on sci.snapshot_id = di.snapshot_id
        and sci.charge_item_id = di.charge_item_id
),

csv_items as (
    select
        r.silver_charge_item_id,
        r.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        cast(null as varchar) as source_charge_item_id,
        min(r.row_ordinal) as source_item_ordinal,
        min(r.row_ordinal) as first_source_row_ordinal,
        max(r.row_ordinal) as last_source_row_ordinal,
        count(*) as source_row_count,
        any_value(r.raw_description) as raw_description,
        r.clean_description,
        r.drug_unit,
        any_value(r.raw_drug_unit_type) as raw_drug_unit_type,
        r.clean_drug_unit_type,
        r.charge_item_signature
    from {{ ref('slv_base__csv_charge_row_items') }} r
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    group by
        r.silver_charge_item_id,
        r.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        r.clean_description,
        r.drug_unit,
        r.clean_drug_unit_type,
        r.charge_item_signature
)

select * from json_items
union all
select * from csv_items
