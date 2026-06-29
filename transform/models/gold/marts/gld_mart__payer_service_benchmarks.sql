-- gld_mart__payer_service_benchmarks
--
-- User question: "For a matched payer, how does this hospital's negotiated dollar
-- compare to the payer's market and to the hospital's own cash price?"
--
-- Grain: one row per (canonical_payer_id, hospital_id, service_code_key,
-- clean_setting, clean_billing_class, modifier_signature). amount_kind is always
-- negotiated_dollar.
--
-- Prerequisite gate (decision 0017): canonical_payer_id is REQUIRED — unmatched /
-- null-payer rows never enter (payer identity gates; plan never gates). market_segment
-- is carried for segment cuts (which require market_segment <> 'unknown') but is a
-- representative value here, not a grain key. Built from the price-ranking subset of
-- gld_mart__service_price_comparison_current (negotiated_dollar only), so it reconciles
-- to that mart.
--
-- Cross-snapshot aggregate → full-refresh table (marts config) reading the
-- comparison mart through plain ref().

with negotiated as (
    select
        canonical_payer_id,
        hospital_id,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        market_segment,
        amount_value
    from {{ ref('gld_mart__service_price_comparison_current') }}
    where is_price_ranking_row = true
        and amount_kind = 'negotiated_dollar'
        and canonical_payer_id is not null
        and canonical_payer_id <> '<unmatched>'
),

-- Hospital's own cash price per service context (for the negotiated-vs-cash delta).
hosp_cash as (
    select
        hospital_id,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        median(amount_value) as hospital_cash_amount
    from {{ ref('gld_mart__service_price_comparison_current') }}
    where is_price_ranking_row = true
        and amount_kind = 'discounted_cash'
    group by 1, 2, 3, 4, 5
),

-- All hospitals reporting a comparable negotiated dollar for the context (matched
-- or not) — the denominator for payer match coverage.
context_hospitals as (
    select
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        count(distinct hospital_id) as context_hospital_count
    from {{ ref('gld_mart__service_price_comparison_current') }}
    where is_price_ranking_row = true
        and amount_kind = 'negotiated_dollar'
    group by 1, 2, 3, 4
),

-- Hospital's representative negotiated dollar per (payer, hospital, context).
hosp_payer as (
    select
        canonical_payer_id,
        hospital_id,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        any_value(market_segment) as market_segment,
        median(amount_value) as negotiated_dollar
    from negotiated
    group by 1, 2, 3, 4, 5, 6
),

-- Payer's market across hospitals for the context (one hosp_payer row per hospital,
-- so count(*) is the matched-hospital count).
payer_market as (
    select
        canonical_payer_id,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        count(*) as payer_hospital_count,
        median(negotiated_dollar) as payer_market_median_negotiated
    from hosp_payer
    group by 1, 2, 3, 4, 5
)

select
    hp.canonical_payer_id,
    dp.canonical_payer_name,
    dp.payer_parent_name,
    dp.payer_type,
    hp.hospital_id,
    hp.service_code_key,
    hp.clean_setting,
    hp.clean_billing_class,
    hp.modifier_signature,
    cast('negotiated_dollar' as varchar) as amount_kind,
    hp.market_segment,

    hp.negotiated_dollar,

    -- negotiated vs the hospital's own cash price
    hc.hospital_cash_amount,
    hp.negotiated_dollar - hc.hospital_cash_amount as delta_from_hospital_cash,
    case
        when hc.hospital_cash_amount <> 0
        then (hp.negotiated_dollar - hc.hospital_cash_amount)
            / hc.hospital_cash_amount
    end as pct_delta_from_hospital_cash,

    -- negotiated vs the payer's service-market median (3-hospital floor)
    pm.payer_hospital_count,
    case
        when pm.payer_hospital_count >= 3 then pm.payer_market_median_negotiated
    end as payer_market_median_negotiated,
    case
        when pm.payer_hospital_count >= 3
        then hp.negotiated_dollar - pm.payer_market_median_negotiated
    end as delta_from_payer_market_median,
    case
        when pm.payer_hospital_count >= 3
            and pm.payer_market_median_negotiated <> 0
        then (hp.negotiated_dollar - pm.payer_market_median_negotiated)
            / pm.payer_market_median_negotiated
    end as pct_delta_from_payer_market_median,

    -- payer match coverage for the context
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
left join context_hospitals as ch
    on hp.service_code_key = ch.service_code_key
    and hp.clean_setting is not distinct from ch.clean_setting
    and hp.clean_billing_class is not distinct from ch.clean_billing_class
    and hp.modifier_signature is not distinct from ch.modifier_signature
left join payer_market as pm
    on hp.canonical_payer_id = pm.canonical_payer_id
    and hp.service_code_key = pm.service_code_key
    and hp.clean_setting is not distinct from pm.clean_setting
    and hp.clean_billing_class is not distinct from pm.clean_billing_class
    and hp.modifier_signature is not distinct from pm.modifier_signature
left join {{ ref('gld_dim__payer') }} as dp
    on hp.canonical_payer_id = dp.canonical_payer_id
