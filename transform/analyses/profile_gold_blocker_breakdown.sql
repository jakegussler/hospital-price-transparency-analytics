-- Profiling: WHY observations are not cross-hospital comparable.
-- Sums the row-level blocker counts from the coverage scorecard (current
-- snapshots) into a ranked, tall breakdown with shares of classified cohorts.
with cov as (
    select *
    from {{ ref('gld__snapshot_coverage_scorecard') }}
    where is_current_snapshot = true
),

totals as (
    select
        sum(tier_0_count + tier_1_count + tier_2_count) as classified_obs_cohorts,
        sum(blocker_code_not_cross_hospital_comparable) as code_not_comparable,
        sum(blocker_code_not_specific) as code_not_specific,
        sum(blocker_missing_match_code) as missing_match_code,
        sum(blocker_non_rankable_amount) as non_rankable_amount,
        sum(blocker_derived_dollar) as derived_dollar,
        sum(blocker_modifier_context_required) as modifier_context_required,
        sum(blocker_drug_unit_context_missing) as drug_unit_context_missing,
        sum(blocker_payer_unmatched) as payer_unmatched,
        sum(blocker_market_segment_unknown) as market_segment_unknown
    from cov
),

unpivoted as (
    select 'code_not_cross_hospital_comparable' as blocker, code_not_comparable as n, classified_obs_cohorts from totals
    union all select 'code_not_specific', code_not_specific, classified_obs_cohorts from totals
    union all select 'missing_match_code', missing_match_code, classified_obs_cohorts from totals
    union all select 'non_rankable_amount', non_rankable_amount, classified_obs_cohorts from totals
    union all select 'derived_dollar', derived_dollar, classified_obs_cohorts from totals
    union all select 'modifier_context_required', modifier_context_required, classified_obs_cohorts from totals
    union all select 'drug_unit_context_missing', drug_unit_context_missing, classified_obs_cohorts from totals
    union all select 'payer_unmatched', payer_unmatched, classified_obs_cohorts from totals
    union all select 'market_segment_unknown', market_segment_unknown, classified_obs_cohorts from totals
)

select
    blocker,
    n as blocked_obs_cohorts,
    round(n / nullif(classified_obs_cohorts, 0)::double, 4) as share_of_classified
from unpivoted
order by blocked_obs_cohorts desc
