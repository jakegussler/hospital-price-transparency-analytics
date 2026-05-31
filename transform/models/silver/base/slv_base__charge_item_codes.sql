with csv_codes as (
    {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
),

code_types as (
    select * from {{ ref('cms_code_types') }}
),

json_codes as (
    select
        {{ hpt_surrogate_key([
            'ci.silver_charge_item_id',
            'c.code_ordinal',
            'c.raw_code',
            'c.raw_code_type'
        ]) }} as silver_charge_item_code_id,
        ci.silver_charge_item_id,
        c.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        c.code_ordinal,
        c.raw_code,
        c.clean_code,
        c.raw_code_type,
        c.clean_code_type,
        ct.code_type as canonical_code_system,
        'json_code_information' as source_code_path
    from {{ ref('stg_bronze__code_information') }} c
    inner join {{ ref('slv_base__charge_items') }} ci
        on c.snapshot_id = ci.snapshot_id
        and c.charge_item_id = ci.source_charge_item_id
    left join code_types ct
        on c.clean_code_type = ct.code_type
),

csv_deduped_codes as (
    select distinct
        row_items.silver_charge_item_id,
        cc.snapshot_id,
        cc.code_ordinal,
        cc.raw_code,
        {{ hpt_clean_display_text('cc.raw_code') }} as clean_code,
        cc.raw_code_type,
        {{ hpt_clean_text('cc.raw_code_type') }} as clean_code_type
    from csv_codes cc
    inner join {{ ref('slv_base__csv_charge_row_items') }} row_items
        on cc.snapshot_id = row_items.snapshot_id
        and cc.row_ordinal = row_items.row_ordinal
),

csv_codes_final as (
    select
        {{ hpt_surrogate_key([
            'ci.silver_charge_item_id',
            'c.code_ordinal',
            'c.raw_code',
            'c.raw_code_type'
        ]) }} as silver_charge_item_code_id,
        ci.silver_charge_item_id,
        c.snapshot_id,
        ci.hospital_id,
        ci.source_format,
        c.code_ordinal,
        c.raw_code,
        c.clean_code,
        c.raw_code_type,
        c.clean_code_type,
        ct.code_type as canonical_code_system,
        'csv_charge_rows' as source_code_path
    from csv_deduped_codes c
    inner join {{ ref('slv_base__charge_items') }} ci
        on c.silver_charge_item_id = ci.silver_charge_item_id
    left join code_types ct
        on c.clean_code_type = ct.code_type
)

select * from json_codes
union all
select * from csv_codes_final
