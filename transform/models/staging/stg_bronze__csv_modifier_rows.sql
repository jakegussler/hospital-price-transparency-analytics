with csv_codes as (
    {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
),

code_flags as (
    select
        snapshot_id,
        row_ordinal,
        count(*) > 0 as has_any_code_component
    from csv_codes
    group by snapshot_id, row_ordinal
),

member_rollup as (
    select
        snapshot_id,
        row_ordinal,
        string_agg(clean_modifier_code, '|' order by member_ordinal) as clean_modifier_combination,
        count(*) as member_count
    from {{ ref('stg_bronze__csv_modifier_members') }}
    group by snapshot_id, row_ordinal
),

source_rows as (
    select
        snapshot_id,
        row_ordinal,
        any_value(source_format) as source_format,
        any_value(raw_description) as raw_description,
        any_value(clean_description) as clean_description,
        any_value(raw_setting) as raw_setting,
        any_value(clean_setting) as clean_setting,
        any_value(raw_modifiers) as raw_modifier_combination
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id, row_ordinal
)

select
    r.*,
    m.clean_modifier_combination,
    coalesce(m.member_count, 0) as member_count,
    coalesce(m.member_count, 0) > 0 as has_modifier,
    coalesce(c.has_any_code_component, false) as has_any_code_component,
    coalesce(m.member_count, 0) > 0
        and not coalesce(c.has_any_code_component, false) as is_standalone_modifier,
    coalesce(m.member_count, 0) > 0
        and coalesce(c.has_any_code_component, false) as is_item_associated_modifier
from source_rows r
left join member_rollup m
    on r.snapshot_id = m.snapshot_id
    and r.row_ordinal = m.row_ordinal
left join code_flags c
    on r.snapshot_id = c.snapshot_id
    and r.row_ordinal = c.row_ordinal
