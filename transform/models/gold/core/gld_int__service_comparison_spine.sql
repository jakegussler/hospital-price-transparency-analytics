-- gld_int__service_comparison_spine
--
-- Retained-snapshot, code-expanded comparison spine. Materializes the expensive
-- observation × comparable-code classification once so current marts and
-- all-snapshot scorecards can read it back instead of rebuilding the join.
--
-- Grain: one row per (gold_rate_observation_id, service_code_key) over every
-- retained snapshot. service_code_key is null for an observation with no
-- cross-hospital-comparable code. Snapshot-grained incremental
-- (snapshot_replace on snapshot_id) so the per-snapshot Gold pass bounds peak
-- memory; current-only retention prunes superseded snapshot partitions while
-- all_snapshots retention preserves them.
--
-- Currentness is carried for observability but can change after this partition
-- was built. Current-only consumers must use
-- gld_int__service_comparison_spine_current, which resolves currentness through
-- gld_dim__snapshot at query time.

with fact as (
    select *
    from {{ hpt_scoped_ref('gld_fct__rate_observations') }}
),

-- Deduplicate comparable cohorts at charge-item grain BEFORE expanding them
-- across amount observations. The observation-level bridge is 20x larger than
-- slv_core__charge_item_codes on the current corpus; applying DISTINCT after
-- that fan-out creates a large blocking aggregate even for one hospital.
item_cohorts as (
    select distinct
        snapshot_id,
        silver_charge_item_id,
        {{ hpt_surrogate_key(['canonical_code_system', 'match_code']) }}
            as service_code_key,
        canonical_code_system,
        match_code,
        code_is_specific
    from {{ hpt_scoped_ref('slv_core__charge_item_codes') }}
    where code_cross_hospital_comparable = true
        and match_code is not null
),

assembled as (
    select
        f.gold_rate_observation_id,
        cohorts.service_code_key,
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
        f.clean_payer_name,
        f.clean_plan_name,
        f.source_contract_key,
        f.contract_identity_precision,
        f.market_segment,
        f.benefit_line,
        f.plan_type,
        f.is_drug_observation,
        f.canonical_drug_unit_type,
        f.drug_unit_status,
        f.is_current_snapshot,
        cohorts.canonical_code_system,
        cohorts.match_code,
        coalesce(cohorts.code_is_specific, false) as code_is_specific,
        (cohorts.service_code_key is not null) as code_cross_hospital_comparable
    from fact as f
    left join item_cohorts as cohorts
        on f.snapshot_id = cohorts.snapshot_id
        and f.silver_charge_item_id = cohorts.silver_charge_item_id
),

classified as (
    select
        *,
        {{ hpt_comparison_tier() }} as comparison_tier,
        {{ hpt_comparison_methodology() }} as comparison_methodology,
        {{ hpt_comparison_blocker_flags() }}
    from assembled
)

select
    *,
    {{ hpt_service_context_key() }} as service_context_key
from classified
