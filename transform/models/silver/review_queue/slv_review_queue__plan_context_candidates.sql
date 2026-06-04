with weak_plan_context as (
    select
        pr.canonical_payer_id,
        pr.canonical_payer_name,
        pr.clean_payer_name,
        pr.raw_payer_name,
        pr.clean_plan_name,
        pr.display_plan_name,
        pr.raw_plan_name,
        pr.hospital_id,
        pr.snapshot_id,
        pr.source_format,
        pr.market_segment,
        pr.plan_type,
        pr.payer_context_match_basis,
        pr.payer_context_confidence,
        snapshots.canonical_state
    from {{ ref('slv_core__payer_rates') }} pr
    left join {{ ref('slv_base__hospital_snapshots') }} snapshots
        on pr.snapshot_id = snapshots.snapshot_id
    where pr.canonical_payer_id is not null
        and pr.clean_plan_name is not null
        and pr.snapshot_id in (
            {{ hpt_current_snapshot_ids_sql() }}
        )
        and (
            pr.market_segment = 'unknown'
            or pr.payer_context_match_basis = 'no_context_rule'
            or pr.payer_context_confidence = 'low'
        )
),

grouped as (
    select
        canonical_payer_id,
        clean_plan_name,
        count(*) as payer_rate_rows,
        count(*) filter (where market_segment = 'unknown') as unknown_market_segment_rows,
        count(*) filter (where payer_context_match_basis = 'no_context_rule') as no_context_rule_rows,
        count(*) filter (where payer_context_confidence = 'low') as low_confidence_context_rows,
        count(*) filter (where plan_type is null) as null_plan_type_rows,
        count(distinct hospital_id) as hospital_count,
        count(distinct snapshot_id) as snapshot_count,
        count(distinct source_format) as source_format_count,
        count(distinct canonical_state) filter (where canonical_state is not null) as state_count,
        count(distinct clean_payer_name) filter (where clean_payer_name is not null) as clean_payer_name_count,
        min(canonical_payer_name) filter (where canonical_payer_name is not null) as canonical_payer_name,
        min(clean_payer_name) filter (where clean_payer_name is not null) as example_clean_payer_name,
        min(raw_payer_name) filter (where raw_payer_name is not null) as example_raw_payer_name,
        min(display_plan_name) filter (where display_plan_name is not null) as example_display_plan_name,
        min(raw_plan_name) filter (where raw_plan_name is not null) as example_raw_plan_name,
        min(canonical_state) filter (where canonical_state is not null) as example_state
    from weak_plan_context
    group by
        canonical_payer_id,
        clean_plan_name
)

select
    {{ hpt_surrogate_key([
        'canonical_payer_id',
        'clean_plan_name'
    ]) }} as plan_context_candidate_key,
    canonical_payer_id,
    canonical_payer_name,
    clean_plan_name,
    example_display_plan_name,
    example_raw_plan_name,
    example_clean_payer_name,
    example_raw_payer_name,
    example_state,
    payer_rate_rows,
    unknown_market_segment_rows,
    no_context_rule_rows,
    low_confidence_context_rows,
    null_plan_type_rows,
    hospital_count,
    snapshot_count,
    source_format_count,
    state_count,
    clean_payer_name_count,
    'needs_review' as review_queue_status
from grouped
order by
    payer_rate_rows desc,
    unknown_market_segment_rows desc,
    hospital_count desc,
    canonical_payer_id,
    clean_plan_name
