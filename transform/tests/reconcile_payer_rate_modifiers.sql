with expected as (
    select
        pr.silver_payer_rate_id,
        m.silver_charge_modifier_member_id
    from {{ ref('slv_base__payer_rates') }} pr
    inner join {{ ref('slv_base__charge_modifier_members') }} m
        on pr.snapshot_id = m.snapshot_id
        and pr.source_row_ordinal = m.source_row_ordinal
    where pr.source_format like 'csv%'
        {{ hpt_snapshot_filter('pr') }}
),

actual as (
    select silver_payer_rate_id, silver_charge_modifier_member_id
    from {{ ref('slv_base__payer_rate_modifiers') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)

select 'missing' as mismatch_type, * from expected
except
select 'missing' as mismatch_type, * from actual

union all

select 'unexpected' as mismatch_type, * from actual
except
select 'unexpected' as mismatch_type, * from expected
