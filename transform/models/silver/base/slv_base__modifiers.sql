with json_member_counts as (
    select
        m.snapshot_id,
        m.modifier_code_id,
        count(*) as member_count
    from {{ ref('stg_bronze__modifiers') }} m
    cross join unnest(string_split(m.raw_modifier_code, '|')) as u(raw_modifier_code)
    where {{ hpt_trimmed_text('u.raw_modifier_code') }} is not null
    group by m.snapshot_id, m.modifier_code_id
),

json_modifiers as (
    select
        {{ hpt_surrogate_key(['m.snapshot_id', "'json_definition'", 'm.modifier_code_id']) }} as silver_modifier_id,
        'json_definition' as definition_kind,
        m.modifier_code_id as source_modifier_code_id,
        cast(null as integer) as source_row_ordinal,
        m.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        m.raw_modifier_code as raw_modifier_combination,
        m.clean_modifier_code as clean_modifier_combination,
        m.raw_description,
        m.clean_description,
        m.raw_setting,
        m.clean_setting,
        coalesce(mc.member_count, 0) as member_count
    from {{ ref('stg_bronze__modifiers') }} m
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on m.snapshot_id = hs.snapshot_id
    left join json_member_counts mc
        on m.snapshot_id = mc.snapshot_id
        and m.modifier_code_id = mc.modifier_code_id
    where not exists (
        select 1
        from {{ ref('val__modifier_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = m.snapshot_id
            and r.modifier_code_id = m.modifier_code_id
    )
),

csv_modifiers as (
    select
        {{ hpt_surrogate_key(['m.snapshot_id', "'csv_standalone_rule'", 'm.row_ordinal']) }} as silver_modifier_id,
        'csv_standalone_rule' as definition_kind,
        cast(null as varchar) as source_modifier_code_id,
        m.row_ordinal as source_row_ordinal,
        m.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        m.raw_modifier_combination,
        m.clean_modifier_combination,
        m.raw_description,
        m.clean_description,
        m.raw_setting,
        m.clean_setting,
        m.member_count
    from {{ ref('stg_bronze__csv_modifier_rows') }} m
    inner join {{ ref('slv_base__hospital_snapshots') }} hs
        on m.snapshot_id = hs.snapshot_id
    where m.is_standalone_modifier
        and not exists (
            select 1
            from {{ ref('val__modifier_rejections') }} r
            where r.source_format_family = 'csv'
                and r.snapshot_id = m.snapshot_id
                and r.row_ordinal = m.row_ordinal
        )
)

select * from json_modifiers
union all
select * from csv_modifiers
