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
        sci.reported_schema_version,
        sci.reported_schema_family,
        sci.parser_schema_family,
        sci.parser_schema_version,
        sci.schema_version_mismatch,
        sci.raw_description,
        sci.clean_description,
        di.drug_unit,
        di.raw_drug_unit_type,
        di.clean_drug_unit_type,
        {{ hpt_surrogate_key(['sci.snapshot_id', "'json'", 'sci.charge_item_id']) }} as charge_item_signature
    from {{ hpt_scoped_ref('stg_bronze__standard_charge_info') }} sci
    inner join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} hs
        on sci.snapshot_id = hs.snapshot_id
    left join {{ hpt_scoped_ref('stg_bronze__drug_information') }} di
        on sci.snapshot_id = di.snapshot_id
        and sci.charge_item_id = di.charge_item_id
        and not exists (
            select 1
            from {{ hpt_scoped_ref('val__drug_rejections') }} r
            where r.source_format_family = 'json'
                and r.snapshot_id = di.snapshot_id
                and r.source_charge_item_id = di.charge_item_id
        )
    where not exists (
        select 1
        from {{ hpt_scoped_ref('val__charge_item_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = sci.snapshot_id
            and r.source_charge_item_id = sci.charge_item_id
    )
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
        cast(null as varchar) as reported_schema_version,
        cast(null as varchar) as reported_schema_family,
        cast(null as varchar) as parser_schema_family,
        cast(null as varchar) as parser_schema_version,
        cast(null as boolean) as schema_version_mismatch,
        any_value(r.raw_description) as raw_description,
        r.clean_description,
        r.drug_unit,
        any_value(r.raw_drug_unit_type) as raw_drug_unit_type,
        r.clean_drug_unit_type,
        r.charge_item_signature
    from {{ hpt_scoped_ref('slv_base__csv_charge_row_items') }} r
    inner join {{ hpt_scoped_ref('slv_base__hospital_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    group by
        r.silver_charge_item_id,
        r.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        reported_schema_version,
        reported_schema_family,
        parser_schema_family,
        parser_schema_version,
        schema_version_mismatch,
        r.clean_description,
        r.drug_unit,
        r.clean_drug_unit_type,
        r.charge_item_signature
)

select * from json_items
union all
select * from csv_items
