-- Profiling: corpus scale + cross-hospital comparability headline.
-- Aggregates the per-snapshot coverage scorecard over current snapshots. Tier
-- counts are at the observation x comparable-cohort grain (decision 0017):
--   tier_0 = trace only, tier_1 = code-backed, tier_2 = context-aligned (the
--   cross-hospital-comparable subset).
with cov as (
    select *
    from {{ ref('gld__snapshot_coverage_scorecard') }}
    where is_current_snapshot = true
),

dim as (
    select count(*) as distinct_comparable_code_cohorts
    from {{ ref('gld_dim__service_code') }}
)

select
    count(distinct cov.hospital_id) as hospitals,
    count(*) as current_snapshots,
    sum(cov.charge_item_count) as charge_items,
    sum(cov.standard_charge_count) as standard_charges,
    sum(cov.payer_rate_count) as payer_rates,
    sum(cov.observation_count) as rate_observations,
    any_value(dim.distinct_comparable_code_cohorts) as distinct_comparable_code_cohorts,
    sum(cov.tier_0_count + cov.tier_1_count + cov.tier_2_count) as classified_obs_cohorts,
    sum(cov.tier_1_count + cov.tier_2_count) as code_backed_obs_cohorts,
    round(
        sum(cov.tier_1_count + cov.tier_2_count)
        / nullif(sum(cov.tier_0_count + cov.tier_1_count + cov.tier_2_count), 0)::double,
        4
    ) as code_backed_rate,
    sum(cov.tier_2_count) as comparable_obs_cohorts,
    round(
        sum(cov.tier_2_count)
        / nullif(sum(cov.tier_0_count + cov.tier_1_count + cov.tier_2_count), 0)::double,
        4
    ) as cross_hospital_comparable_rate
from cov
cross join dim
