-- gld_score__snapshot_coverage_scorecard (plan §8.1)
--
-- Grain: one row per snapshot_id. Purpose: rank TRUST before price, and double as
-- the Gold-side reconciliation anchor — its atomic observation/charge/rate counts
-- are taken straight from the fact (no code fan-out), so they reconcile to
-- gld_fct__rate_observations by construction (see tests/gld_coverage_reconciles_to_fact.sql).
--
-- Two count sources, joined per snapshot:
--   * fact_agg       — atomic counts + amount-kind coverage from the fact.
--   * comparison_agg — code-cohort, tier, and row-level blocker counts re-derived
--     from fact ⋈ bridge through the §6 framework macros (the same classification
--     the comparison mart applies), so the scorecard explains blocked rows with the
--     identical vocabulary. Computed over ALL snapshots (not current-only) so
--     non-current snapshots are still scored. below_min_hospital_denominator is a
--     mart-grain (window) blocker and is intentionally not counted here.
--
-- Cross-snapshot aggregate → full-refresh table (gold.scorecards config block)
-- reading the fact and bridge through plain ref(); excluded from the snapshot prune.

with fact_agg as (
    select
        snapshot_id,
        any_value(hospital_id) as hospital_id,
        count(distinct silver_charge_item_id) as charge_item_count,
        count(distinct silver_standard_charge_id) as standard_charge_count,
        count(distinct silver_payer_rate_id) as payer_rate_count,
        count(*) as observation_count,
        sum((amount_kind = 'gross_charge')::int) as obs_gross_charge,
        sum((amount_kind = 'discounted_cash')::int) as obs_discounted_cash,
        sum((amount_kind = 'min_negotiated')::int) as obs_min_negotiated,
        sum((amount_kind = 'max_negotiated')::int) as obs_max_negotiated,
        sum((amount_kind = 'negotiated_dollar')::int) as obs_negotiated_dollar,
        sum((amount_kind = 'negotiated_percentage')::int) as obs_negotiated_percentage,
        sum((amount_kind = 'negotiated_algorithm')::int) as obs_negotiated_algorithm,
        sum((amount_kind = 'estimated_amount')::int) as obs_estimated_amount,
        sum((amount_kind = 'median_amount')::int) as obs_median_amount,
        sum((amount_kind = 'p10_amount')::int) as obs_p10_amount,
        sum((amount_kind = 'p90_amount')::int) as obs_p90_amount,
        sum((amount_unit = 'usd')::int) as dollar_observation_count,
        sum((
            amount_kind = 'negotiated_dollar'
            and amount_comparability_tier = 'comparable_dollar'
        )::int) as comparable_dollar_count,
        sum((
            amount_kind = 'negotiated_dollar'
            and amount_comparability_tier = 'derived_dollar'
        )::int) as derived_dollar_count,
        count(distinct case
            when observation_scope = 'payer_rate'
                and canonical_payer_id is not null
                and canonical_payer_id <> '<unmatched>'
            then silver_payer_rate_id
        end) as matched_payer_rate_count,
        count(distinct case
            when has_modifier then silver_standard_charge_id
        end) as modifier_bearing_charge_count
    from {{ ref('gld_fct__rate_observations') }}
    group by snapshot_id
),

-- Re-derive comparison tier + row-level blockers + code-cohort coverage from
-- fact ⋈ bridge using macros (same classification as
-- gld_mart__service_price_comparison_current, minus the current-only filter and peer
-- windows). Grain: observation × comparable cohort, tier_0 collapse via the left
-- join — identical to the mart and the gld_int spine.
comparison_cohorts as (
    select distinct
        gold_rate_observation_id,
        service_code_key,
        match_code,
        code_is_specific
    from {{ ref('gld_bridge__rate_observation_code') }}
    where service_code_key is not null
),

comparison_assembled as (
    select
        f.snapshot_id,
        f.silver_charge_item_id,
        f.is_current_snapshot,
        f.amount_unit,
        f.amount_role,
        f.amount_comparability_tier,
        f.has_pro_tech_split_modifier,
        f.is_drug_observation,
        f.drug_unit_status,
        f.observation_scope,
        f.canonical_payer_id,
        f.market_segment,
        f.clean_setting,
        f.clean_billing_class,
        cc.service_code_key,
        cc.match_code,
        coalesce(cc.code_is_specific, false) as code_is_specific,
        (cc.service_code_key is not null) as code_cross_hospital_comparable
    from {{ ref('gld_fct__rate_observations') }} as f
    left join comparison_cohorts as cc
        on f.gold_rate_observation_id = cc.gold_rate_observation_id
),

comparison_classified as (
    select
        snapshot_id,
        silver_charge_item_id,
        service_code_key,
        code_cross_hospital_comparable,
        {{ hpt_comparison_tier() }} as comparison_tier,
        {{ hpt_comparison_blocker_flags() }}
    from comparison_assembled
),

comparison_agg as (
    select
        snapshot_id,
        count(distinct service_code_key) as distinct_comparable_codes,
        count(distinct case
            when code_cross_hospital_comparable then silver_charge_item_id
        end) as items_with_comparable_code,
        sum((comparison_tier = 'tier_0_trace_only')::int) as tier_0_count,
        sum((comparison_tier = 'tier_1_code_backed')::int) as tier_1_count,
        sum((comparison_tier = 'tier_2_context_aligned')::int) as tier_2_count,
        sum(not_current_snapshot::int) as blocker_not_current_snapshot,
        sum(code_not_cross_hospital_comparable::int) as blocker_code_not_cross_hospital_comparable,
        sum(code_not_specific::int) as blocker_code_not_specific,
        sum(missing_match_code::int) as blocker_missing_match_code,
        sum(non_rankable_amount::int) as blocker_non_rankable_amount,
        sum(derived_dollar::int) as blocker_derived_dollar,
        sum(modifier_context_required::int) as blocker_modifier_context_required,
        sum(drug_unit_context_missing::int) as blocker_drug_unit_context_missing,
        sum(payer_unmatched::int) as blocker_payer_unmatched,
        sum(market_segment_unknown::int) as blocker_market_segment_unknown
    from comparison_classified
    group by snapshot_id
)

select
    f.snapshot_id,
    f.hospital_id,
    ds.is_current_snapshot,
    ds.published_last_updated_on,
    ds.snapshot_age_days,
    ds.freshness_bucket,

    -- record counts (reconcile to the fact)
    f.charge_item_count,
    f.standard_charge_count,
    f.payer_rate_count,
    f.observation_count,

    -- observation counts by amount_kind
    f.obs_gross_charge,
    f.obs_discounted_cash,
    f.obs_min_negotiated,
    f.obs_max_negotiated,
    f.obs_negotiated_dollar,
    f.obs_negotiated_percentage,
    f.obs_negotiated_algorithm,
    f.obs_estimated_amount,
    f.obs_median_amount,
    f.obs_p10_amount,
    f.obs_p90_amount,

    -- code coverage
    c.distinct_comparable_codes,
    c.items_with_comparable_code,
    c.items_with_comparable_code / nullif(f.charge_item_count, 0)::double
        as coded_item_coverage_rate,

    -- dollar / amount-kind coverage
    f.dollar_observation_count,
    f.dollar_observation_count / nullif(f.observation_count, 0)::double
        as dollar_observation_coverage_rate,
    f.obs_discounted_cash / nullif(f.standard_charge_count, 0)::double
        as discounted_cash_coverage_rate,
    f.obs_negotiated_dollar / nullif(f.payer_rate_count, 0)::double
        as negotiated_dollar_coverage_rate,
    f.comparable_dollar_count,
    f.derived_dollar_count,

    -- payer mapping
    f.matched_payer_rate_count,
    f.matched_payer_rate_count / nullif(f.payer_rate_count, 0)::double
        as payer_mapping_coverage_rate,

    -- modifiers
    f.modifier_bearing_charge_count,

    -- comparison tier counts (observation × comparable cohort grain)
    c.tier_0_count,
    c.tier_1_count,
    c.tier_2_count,

    -- blocker-reason counts
    c.blocker_not_current_snapshot,
    c.blocker_code_not_cross_hospital_comparable,
    c.blocker_code_not_specific,
    c.blocker_missing_match_code,
    c.blocker_non_rankable_amount,
    c.blocker_derived_dollar,
    c.blocker_modifier_context_required,
    c.blocker_drug_unit_context_missing,
    c.blocker_payer_unmatched,
    c.blocker_market_segment_unknown
from fact_agg as f
left join comparison_agg as c
    on f.snapshot_id = c.snapshot_id
left join {{ ref('gld_dim__snapshot') }} as ds
    on f.snapshot_id = ds.snapshot_id
