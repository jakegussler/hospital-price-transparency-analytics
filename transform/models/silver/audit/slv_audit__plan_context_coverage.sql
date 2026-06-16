-- Plan / payer-context coverage metrics by canonical payer (Phase 3 of the
-- plan-normalization design). Measures how much of the current payer-rate
-- corpus carries a resolved market_segment and a populated plan_type, and how
-- each was resolved (curated rule vs. deterministic derivation). Scoped to
-- current snapshots so superseded snapshots do not double-count under
-- all_snapshots retention. A human-readable observability view, not a review
-- queue: slv_review_queue__plan_context_candidates ranks the specific
-- payer/plan combos to curate next. The plan's three headline metrics
-- (% rows with market_segment resolved, % distinct combos resolved, % rows
-- with plan_type populated) are recoverable by summing across this grain.
with current_snapshots as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
    where is_current_snapshot = true
),

scoped_rates as (
    select
        coalesce(pr.canonical_payer_id, '<unmatched_payer>') as canonical_payer_id,
        pr.canonical_payer_name,
        pr.clean_plan_name,
        pr.market_segment,
        pr.plan_type,
        pr.plan_type_basis,
        pr.payer_context_match_basis,
        pr.hospital_id,
        pr.snapshot_id
    from {{ ref('slv_core__payer_rates') }} pr
    inner join current_snapshots cs
        on pr.snapshot_id = cs.snapshot_id
)

select
    canonical_payer_id,
    min(canonical_payer_name) as canonical_payer_name,
    count(*) as payer_rate_rows,
    -- market_segment coverage
    count(*) filter (where market_segment <> 'unknown') as market_segment_resolved_rows,
    round(
        100.0 * count(*) filter (where market_segment <> 'unknown') / count(*), 2
    ) as pct_market_segment_resolved,
    count(*) filter (
        where payer_context_match_basis = 'payer_context_rule'
    ) as context_rule_rows,
    round(
        100.0 * count(*) filter (
            where payer_context_match_basis = 'payer_context_rule'
        ) / count(*), 2
    ) as pct_context_rule_applied,
    -- plan_type coverage and provenance
    count(*) filter (where plan_type is not null) as plan_type_populated_rows,
    round(
        100.0 * count(*) filter (where plan_type is not null) / count(*), 2
    ) as pct_plan_type_populated,
    count(*) filter (
        where plan_type_basis = 'payer_context_rule'
    ) as plan_type_rule_rows,
    count(*) filter (
        where plan_type_basis = 'derived_plan_type'
    ) as plan_type_derived_rows,
    -- combo-level coverage (a combo counts as resolved when any row resolves)
    count(distinct clean_plan_name) as distinct_plan_names,
    count(distinct clean_plan_name) filter (
        where market_segment <> 'unknown'
    ) as distinct_plan_names_segment_resolved,
    count(distinct hospital_id) as hospital_count,
    count(distinct snapshot_id) as snapshot_count
from scoped_rates
group by canonical_payer_id
order by payer_rate_rows desc
