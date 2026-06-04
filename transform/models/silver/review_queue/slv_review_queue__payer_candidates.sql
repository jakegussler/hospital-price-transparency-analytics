with unmatched_payers as (
    select
        pr.clean_payer_name,
        pr.raw_payer_name,
        pr.clean_plan_name,
        pr.raw_plan_name,
        pr.hospital_id,
        pr.snapshot_id,
        pr.source_format,
        snapshots.canonical_state
    from {{ ref('slv_base__payer_rates') }} pr
    left join {{ ref('slv_core__payer_rates') }} core
        on pr.silver_payer_rate_id = core.silver_payer_rate_id
    left join {{ ref('slv_base__hospital_snapshots') }} snapshots
        on pr.snapshot_id = snapshots.snapshot_id
    where pr.clean_payer_name is not null
        and core.canonical_payer_id is null
        and pr.snapshot_id in (
            {{ hpt_current_snapshot_ids_sql() }}
        )
),

grouped as (
    select
        clean_payer_name,
        count(*) as payer_rate_rows,
        count(distinct hospital_id) as hospital_count,
        count(distinct snapshot_id) as snapshot_count,
        count(distinct source_format) as source_format_count,
        count(distinct canonical_state) filter (where canonical_state is not null) as state_count,
        count(distinct clean_plan_name) filter (where clean_plan_name is not null) as distinct_clean_plan_names,
        min(raw_payer_name) as example_raw_payer_name,
        min(clean_plan_name) filter (where clean_plan_name is not null) as example_clean_plan_name,
        min(raw_plan_name) filter (where raw_plan_name is not null) as example_raw_plan_name,
        min(canonical_state) filter (where canonical_state is not null) as example_state
    from unmatched_payers
    group by clean_payer_name
)

select
    {{ hpt_surrogate_key(['clean_payer_name']) }} as payer_candidate_key,
    clean_payer_name,
    example_raw_payer_name,
    example_clean_plan_name,
    example_raw_plan_name,
    example_state,
    payer_rate_rows,
    hospital_count,
    snapshot_count,
    source_format_count,
    state_count,
    distinct_clean_plan_names,
    'needs_review' as review_queue_status
from grouped
order by
    payer_rate_rows desc,
    hospital_count desc,
    clean_payer_name
