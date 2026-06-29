-- gld_int__service_comparison_spine
--
-- Intermediate for gld_mart__service_price_comparison_current. Materializes the
-- code-expanded, blocker-annotated "expanded spine" (fact ⋈ bridge + the
-- comparison_tier / blocker classification) as its OWN table so the comparison
-- mart's many peer cuts read it back instead of rebuilding it.
--
-- Why this is a separate table (memory): the spine is ~one row per
-- (observation × comparable code cohort) over every current snapshot. 
-- The comparison mart references the classified spine five times:
-- rankable, peer_stats, payer_rankable, payer_peer_stats, and scored.
-- DuckDB inlines CTEs, so as a single in-model CTE the fact ⋈ obs_cohorts hash
-- join was rebuilt once per reference and pipelined concurrently, holding
-- several multi-GB hash tables at once. Persisting the spine once
-- and letting each consumer do a narrow, projection-pushed-down
-- columnar scan collapses peak memory. Grain and classification are identical to
-- the inline version; only the materialization boundary changed.
--
-- Grain: one row per (gold_rate_observation_id, service_code_key) over current
-- snapshots (service_code_key null for observations with no cross-hospital
-- comparable code). Same current-only inclusion and all-tiers-retained rule as
-- the consuming mart.

with fact as (
    select *
    from {{ ref('gld_fct__rate_observations') }}
    where is_current_snapshot = true
),

-- One row per observation × comparable code cohort. Non-comparable / null-keyed
-- bridge rows carry a null service_code_key and are excluded here, so observations
-- with no comparable code collapse to a single tier_0 row per observation via the
-- left join below (keeping the (observation, service_code_key) grain clean).
obs_cohorts as (
    select distinct
        gold_rate_observation_id,
        service_code_key,
        canonical_code_system,
        match_code,
        code_is_specific
    from {{ ref('gld_bridge__rate_observation_code') }}
    where service_code_key is not null
),

assembled as (
    select
        f.gold_rate_observation_id,
        oc.service_code_key,
        f.snapshot_id,
        f.hospital_id,
        f.observation_scope,
        f.silver_standard_charge_id,
        f.silver_charge_item_id,
        f.silver_payer_rate_id,
        f.amount_kind,
        f.amount_role,
        f.amount_unit,
        f.amount_value,
        f.is_price_rankable,
        f.methodology,
        f.amount_comparability_tier,
        f.clean_setting,
        f.clean_billing_class,
        f.modifier_signature,
        f.has_pro_tech_split_modifier,
        f.canonical_payer_id,
        f.market_segment,
        f.benefit_line,
        f.plan_type,
        f.is_drug_observation,
        f.canonical_drug_unit_type,
        f.drug_unit_status,
        f.is_current_snapshot,
        oc.canonical_code_system,
        oc.match_code,
        coalesce(oc.code_is_specific, false) as code_is_specific,
        (oc.service_code_key is not null) as code_cross_hospital_comparable
    from fact as f
    left join obs_cohorts as oc
        on f.gold_rate_observation_id = oc.gold_rate_observation_id
)

-- Comparison classification (plan §6): tier + the row-level blocker flags.
select
    *,
    {{ hpt_comparison_tier() }} as comparison_tier,
    {{ hpt_comparison_blocker_flags() }}
from assembled
