-- gld_int__service_contract_representatives
--
-- Contract-level representative amounts (decision 0021, level 1 of the market
-- statistic hierarchy). Grain: one row per (hospital_id, snapshot_id,
-- service_context_key, source_contract_key) over the negotiated-dollar
-- price-ranking subset of the authoritative current-spine view (tier_2 +
-- is_price_rankable, current snapshots only).
--
-- Exact repetitions of one amount inside a contract/context collapse to ONE
-- representative (the fix for one hospital repeating a per-diem rate across 56
-- revenue-code variants and receiving 56 statistical votes). A contract/context
-- with MULTIPLE distinct amounts is a hidden-context ambiguity (often a
-- revenue-code or network distinction the comparison key does not model): it is
-- flagged has_multiple_contract_amounts and gets NO representative — visible,
-- never silently averaged (strict rule; on the profiled corpus 94.8% of
-- contract/contexts have exactly one distinct amount).
--
-- Cross-snapshot aggregate → full-refresh table (marts config), same
-- materialization rationale as gld_int__service_comparison_spine: the hospital
-- representative layer and the payer benchmarks each read it back.

with ranking_rows as (
    select
        hospital_id,
        snapshot_id,
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,
        source_contract_key,
        contract_identity_precision,
        clean_payer_name,
        clean_plan_name,
        canonical_payer_id,
        market_segment,
        silver_charge_item_id,
        amount_value
    from {{ ref('gld_int__service_comparison_spine_current') }}
    where comparison_tier = 'tier_2_context_aligned'
        and is_price_rankable = true
        and amount_kind = 'negotiated_dollar'
)

select
    hospital_id,
    snapshot_id,
    service_context_key,
    service_code_key,
    clean_setting,
    clean_billing_class,
    modifier_signature,
    amount_kind,
    comparison_methodology,
    canonical_drug_unit_type,
    source_contract_key,
    -- Functionally dependent on source_contract_key (built from these labels);
    -- any_value is a safe carry, not an aggregation decision.
    any_value(contract_identity_precision) as contract_identity_precision,
    any_value(clean_payer_name) as clean_payer_name,
    any_value(clean_plan_name) as clean_plan_name,
    any_value(canonical_payer_id) as canonical_payer_id,
    any_value(market_segment) as market_segment,
    count(*) as raw_observation_count,
    count(distinct amount_value) as distinct_amount_count,
    count(distinct silver_charge_item_id) as distinct_charge_item_count,
    min(amount_value) as contract_amount_min,
    max(amount_value) as contract_amount_max,
    -- One distinct amount -> it IS the representative. Multiple -> none.
    case
        when count(distinct amount_value) = 1 then min(amount_value)
    end as contract_representative_amount,
    (count(distinct amount_value) > 1) as has_multiple_contract_amounts
from ranking_rows
group by
    hospital_id, snapshot_id, service_context_key, service_code_key,
    clean_setting, clean_billing_class, modifier_signature, amount_kind,
    comparison_methodology, canonical_drug_unit_type, source_contract_key
