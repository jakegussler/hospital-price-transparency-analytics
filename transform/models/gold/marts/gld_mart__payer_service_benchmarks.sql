-- gld_mart__payer_service_benchmarks
--
-- User question: "For a matched payer, how does this hospital's negotiated dollar
-- compare to the payer's market and to the hospital's own cash price?"
--
-- Grain: one row per (canonical_payer_id, hospital_id, service_context_key) =
-- payer × hospital × exact comparison context (code cohort + setting + billing
-- class + modifier signature + amount kind + comparison_methodology + drug unit
-- context). amount_kind is always negotiated_dollar.
--
-- Decision 0021: built from contract representatives
-- (gld_int__service_contract_representatives) — one representative per source
-- contract, one payer-hospital representative per exact context (median of the
-- payer's valid contract representatives), one payer-market distribution over
-- those hospital representatives. Methodology is part of the grain, so a payer's
-- per-diem contracts never enter the same market as its case rates. A
-- payer-hospital context whose contracts are ALL ambiguous keeps its row with a
-- null negotiated_dollar and cash_comparison_status = 'ambiguous_negotiated_context'
-- (visible, blocked from every statistic — a blocker, never a hidden WHERE).
--
-- Cash comparisons carry cash_comparison_status: per-diem rates are NEVER
-- labeled above/below cash (a daily payment vs. an item/episode amount), and
-- deltas are published only for 'comparable' rows.
--
-- Prerequisite gate (decision 0017): canonical_payer_id is REQUIRED — unmatched /
-- null-payer rows never enter (payer identity gates; plan never gates).
-- market_segment is a representative value for segment cuts, not a grain key.
--
-- Cross-snapshot aggregate → full-refresh table (marts config) reading the
-- decision 0021 representative intermediates through plain ref().

with matched_contracts as (
    select
        canonical_payer_id,
        hospital_id,
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,
        market_segment,
        contract_representative_amount,
        has_multiple_contract_amounts
    from {{ ref('gld_int__service_contract_representatives') }}
    where canonical_payer_id is not null
        and canonical_payer_id <> '<unmatched>'
),

-- Hospital's own cash representative per service context (for the
-- negotiated-vs-cash delta): the decision 0021 hospital representative, keyed by
-- the shared context components (the cash context differs in amount_kind /
-- methodology, so the join is on components, not service_context_key).
hosp_cash as (
    select
        hospital_id,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        canonical_drug_unit_type,
        hospital_amount as hospital_cash_amount
    from {{ ref('gld_int__hospital_service_amounts') }}
    where amount_kind = 'discounted_cash'
        and hospital_amount is not null
),

-- All hospitals with a VALID negotiated representative for the exact context
-- (any payer) — the denominator for payer match coverage.
context_hospitals as (
    select
        service_context_key,
        count(*) as context_hospital_count
    from {{ ref('gld_int__hospital_service_amounts') }}
    where amount_kind = 'negotiated_dollar'
        and hospital_amount is not null
    group by 1
),

-- Payer-hospital representative per exact context: median of the payer's VALID
-- contract representatives (median ignores nulls; a context with only ambiguous
-- contracts yields a null representative and stays visible).
hosp_payer as (
    select
        canonical_payer_id,
        hospital_id,
        service_context_key,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        comparison_methodology,
        canonical_drug_unit_type,
        any_value(market_segment) as market_segment,
        count(*) as source_contract_count,
        count(contract_representative_amount) as valid_contract_count,
        count(*) filter (where has_multiple_contract_amounts)
            as ambiguous_contract_count,
        median(contract_representative_amount) as negotiated_dollar
    from matched_contracts
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
),

-- Payer's market across hospitals for the exact context (one representable
-- hosp_payer row per hospital, so count(*) is the matched-hospital count).
payer_market as (
    select
        canonical_payer_id,
        service_context_key,
        count(*) as payer_hospital_count,
        median(negotiated_dollar) as payer_market_median_negotiated
    from hosp_payer
    where negotiated_dollar is not null
    group by 1, 2
)

select
    hp.canonical_payer_id,
    dp.canonical_payer_name,
    dp.payer_parent_name,
    dp.payer_type,
    hp.hospital_id,
    hp.service_context_key,
    hp.service_code_key,
    hp.clean_setting,
    hp.clean_billing_class,
    hp.modifier_signature,
    hp.amount_kind,
    hp.comparison_methodology,
    hp.canonical_drug_unit_type,
    hp.market_segment,

    hp.negotiated_dollar,
    hp.source_contract_count,
    hp.valid_contract_count,
    hp.ambiguous_contract_count,

    -- negotiated vs the hospital's own cash price, guarded by methodology
    -- compatibility (decision 0021)
    case
        when hp.negotiated_dollar is null then 'ambiguous_negotiated_context'
        when hp.comparison_methodology = 'per diem' then 'per_diem_incompatible'
        when hc.hospital_cash_amount is null then 'cash_unavailable'
        else 'comparable'
    end as cash_comparison_status,
    hc.hospital_cash_amount,
    case
        when hp.negotiated_dollar is not null
            and hp.comparison_methodology <> 'per diem'
        then hp.negotiated_dollar - hc.hospital_cash_amount
    end as delta_from_hospital_cash,
    case
        when hp.negotiated_dollar is not null
            and hp.comparison_methodology <> 'per diem'
            and hc.hospital_cash_amount <> 0
        then (hp.negotiated_dollar - hc.hospital_cash_amount)
            / hc.hospital_cash_amount
    end as pct_delta_from_hospital_cash,

    -- negotiated vs the payer's service-market median (3-hospital floor over
    -- hospitals with valid representatives)
    pm.payer_hospital_count,
    case
        when hp.negotiated_dollar is not null and pm.payer_hospital_count >= 3
        then pm.payer_market_median_negotiated
    end as payer_market_median_negotiated,
    case
        when hp.negotiated_dollar is not null and pm.payer_hospital_count >= 3
        then hp.negotiated_dollar - pm.payer_market_median_negotiated
    end as delta_from_payer_market_median,
    case
        when hp.negotiated_dollar is not null
            and pm.payer_hospital_count >= 3
            and pm.payer_market_median_negotiated <> 0
        then (hp.negotiated_dollar - pm.payer_market_median_negotiated)
            / pm.payer_market_median_negotiated
    end as pct_delta_from_payer_market_median,

    -- payer match coverage for the exact context
    ch.context_hospital_count,
    pm.payer_hospital_count / nullif(ch.context_hospital_count, 0)::double
        as payer_match_coverage_rate
from hosp_payer as hp
left join hosp_cash as hc
    on hp.hospital_id = hc.hospital_id
    and hp.service_code_key = hc.service_code_key
    and hp.clean_setting is not distinct from hc.clean_setting
    and hp.clean_billing_class is not distinct from hc.clean_billing_class
    and hp.modifier_signature is not distinct from hc.modifier_signature
    and hp.canonical_drug_unit_type is not distinct from hc.canonical_drug_unit_type
left join context_hospitals as ch
    on hp.service_context_key = ch.service_context_key
left join payer_market as pm
    on hp.canonical_payer_id = pm.canonical_payer_id
    and hp.service_context_key = pm.service_context_key
left join {{ ref('gld_dim__payer') }} as dp
    on hp.canonical_payer_id = dp.canonical_payer_id
