with json_drugs as (
    select
        {{ hpt_surrogate_key(['ci.silver_charge_item_id', "'json'"]) }} as silver_drug_information_id,
        ci.silver_charge_item_id,
        d.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        ci.source_charge_item_id,
        cast(null as integer) as source_row_ordinal,
        d.drug_unit,
        d.raw_drug_unit_type,
        d.clean_drug_unit_type
    from {{ ref('stg_bronze__drug_information') }} d
    inner join {{ ref('slv_base__charge_items') }} ci
        on d.snapshot_id = ci.snapshot_id
        and d.charge_item_id = ci.source_charge_item_id
    where not exists (
        select 1
        from {{ ref('val__drug_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = d.snapshot_id
            and r.source_charge_item_id = d.charge_item_id
    )
),

csv_drugs as (
    select distinct
        {{ hpt_surrogate_key(['ri.silver_charge_item_id', "'csv'", 'ri.row_ordinal']) }} as silver_drug_information_id,
        ri.silver_charge_item_id,
        ri.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        cast(null as varchar) as source_charge_item_id,
        ri.row_ordinal as source_row_ordinal,
        ri.drug_unit,
        ri.raw_drug_unit_type,
        ri.clean_drug_unit_type
    from {{ ref('slv_base__csv_charge_row_items') }} ri
    inner join {{ ref('slv_base__charge_items') }} ci
        on ri.silver_charge_item_id = ci.silver_charge_item_id
    where ri.drug_unit is not null or ri.clean_drug_unit_type is not null
)

select * from json_drugs
union all
select * from csv_drugs
