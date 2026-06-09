with expected as (
    select mr.snapshot_id, mr.row_ordinal
    from {{ ref('stg_bronze__csv_modifier_rows') }} mr
    where mr.is_standalone_modifier
        and not exists (
            select 1
            from {{ ref('val__modifier_rejections') }} r
            where r.source_format_family = 'csv'
                and r.snapshot_id = mr.snapshot_id
                and r.row_ordinal = mr.row_ordinal
        )
        {{ hpt_snapshot_filter('mr') }}
),

actual as (
    select snapshot_id, source_row_ordinal as row_ordinal
    from {{ ref('slv_base__modifiers') }}
    where definition_kind = 'csv_standalone_rule'
        {{ hpt_snapshot_filter() }}
)

select 'missing' as mismatch_type, * from expected
except
select 'missing' as mismatch_type, * from actual

union all

select 'unexpected' as mismatch_type, * from actual
except
select 'unexpected' as mismatch_type, * from expected
