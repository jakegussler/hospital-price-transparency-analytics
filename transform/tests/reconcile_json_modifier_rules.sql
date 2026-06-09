with expected as (
    select m.snapshot_id, m.modifier_code_id as source_modifier_code_id
    from {{ ref('stg_bronze__modifiers') }} m
    where not exists (
        select 1
        from {{ ref('val__modifier_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = m.snapshot_id
            and r.modifier_code_id = m.modifier_code_id
    )
        {{ hpt_snapshot_filter('m') }}
),

actual as (
    select snapshot_id, source_modifier_code_id
    from {{ ref('slv_base__modifiers') }}
    where definition_kind = 'json_definition'
        {{ hpt_snapshot_filter() }}
)

select 'missing' as mismatch_type, * from expected
except
select 'missing' as mismatch_type, * from actual

union all

select 'unexpected' as mismatch_type, * from actual
except
select 'unexpected' as mismatch_type, * from expected
