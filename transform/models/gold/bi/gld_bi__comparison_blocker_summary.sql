-- gld_bi__comparison_blocker_summary
--
-- BI presentation surface for explaining why published rows do or do not reach
-- stricter comparison use cases. Grain: one row per snapshot/blocker_code.
-- Counts come from gld_score__snapshot_coverage_scorecard, preserving the same blocker
-- vocabulary as the comparison framework.

with coverage as (
    select *
    from {{ ref('gld_score__snapshot_coverage_scorecard') }}
),

blockers as (
    select
        snapshot_id,
        hospital_id,
        is_current_snapshot,
        freshness_bucket,
        tier_0_count,
        tier_1_count,
        tier_2_count,
        'not_current_snapshot' as blocker_code,
        'Snapshot is not current' as blocker_label,
        'snapshot_freshness' as blocker_category,
        blocker_not_current_snapshot as blocked_row_count
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'code_not_cross_hospital_comparable',
        'No cross-hospital-comparable code',
        'code_comparability',
        blocker_code_not_cross_hospital_comparable
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'code_not_specific',
        'Comparable code is not specific enough',
        'code_comparability',
        blocker_code_not_specific
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'missing_match_code',
        'Missing normalized code match key',
        'code_comparability',
        blocker_missing_match_code
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'non_rankable_amount',
        'Amount is not a directly rankable dollar price',
        'amount_semantics',
        blocker_non_rankable_amount
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'derived_dollar',
        'Dollar value is derived rather than direct',
        'amount_semantics',
        blocker_derived_dollar
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'modifier_context_required',
        'Modifier context must remain isolated',
        'service_context',
        blocker_modifier_context_required
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'drug_unit_context_missing',
        'Drug observation is missing unit context',
        'service_context',
        blocker_drug_unit_context_missing
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'payer_unmatched',
        'Payer-rate observation has no canonical payer',
        'payer_identity',
        blocker_payer_unmatched
    from coverage
    union all
    select
        snapshot_id, hospital_id, is_current_snapshot, freshness_bucket,
        tier_0_count, tier_1_count, tier_2_count,
        'market_segment_unknown',
        'Market segment is unknown',
        'payer_context',
        blocker_market_segment_unknown
    from coverage
)

select
    b.snapshot_id,
    b.hospital_id,
    h.canonical_hospital_name as hospital_display_name,
    h.health_system,
    h.hospital_type,
    h.canonical_state,
    ds.source_format,
    b.is_current_snapshot,
    b.freshness_bucket,
    b.blocker_code,
    b.blocker_label,
    b.blocker_category,
    b.blocked_row_count,
    b.tier_0_count + b.tier_1_count + b.tier_2_count as classified_row_count,
    b.blocked_row_count
        / nullif(b.tier_0_count + b.tier_1_count + b.tier_2_count, 0)::double
        as blocked_row_share
from blockers as b
left join {{ ref('gld_dim__hospital') }} as h
    on b.hospital_id = h.hospital_id
left join {{ ref('gld_dim__snapshot') }} as ds
    on b.snapshot_id = ds.snapshot_id
