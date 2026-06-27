-- gld__hospital_service_benchmarks
--
-- User question: "For a given service + context, how does THIS hospital's price
-- compare to the market and to its peer groups?"
--
-- Grain: one row per (hospital_id, service_code_key, clean_setting,
-- clean_billing_class, modifier_signature, amount_kind). Built from the
-- price-ranking subset of gld__service_price_comparison_current
-- (is_price_ranking_row = true), so it reconciles to that mart and inherits its
-- current-only, tier_2 + dollar-rankable inclusion.
--
-- The hospital's representative amount per context is the MEDIAN of its rankable
-- observations there (a hospital can report many — e.g. several payer rates for one
-- negotiated_dollar context). Market comparison is published for four peer groups —
-- all, same state, same hospital_type, same health_system — each gated by its own
-- 3-hospital denominator (decision 0017): below the floor, that peer group's stats
-- are null but the row and its hospital_amount still appear.
--
-- Cross-snapshot aggregate → full-refresh table (marts config) reading the
-- comparison mart through plain ref().

with base as (
    select
        hospital_id,
        canonical_state,
        hospital_type,
        health_system,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        amount_value
    from {{ ref('gld__service_price_comparison_current') }}
    where is_price_ranking_row = true
),

-- One row per hospital per service context: the hospital's representative amount.
hosp_amounts as (
    select
        hospital_id,
        canonical_state,
        hospital_type,
        health_system,
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        median(amount_value) as hospital_amount
    from base
    group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),

-- Per-hospital percentile rank within each peer group.
ranked as (
    select
        *,
        percent_rank() over (
            partition by service_code_key, clean_setting, clean_billing_class,
                modifier_signature, amount_kind
            order by hospital_amount
        ) as amount_pct_rank_all,
        percent_rank() over (
            partition by service_code_key, clean_setting, clean_billing_class,
                modifier_signature, amount_kind, canonical_state
            order by hospital_amount
        ) as amount_pct_rank_state,
        percent_rank() over (
            partition by service_code_key, clean_setting, clean_billing_class,
                modifier_signature, amount_kind, hospital_type
            order by hospital_amount
        ) as amount_pct_rank_type,
        percent_rank() over (
            partition by service_code_key, clean_setting, clean_billing_class,
                modifier_signature, amount_kind, health_system
            order by hospital_amount
        ) as amount_pct_rank_system
    from hosp_amounts
),

-- Peer-group medians + hospital counts (one hosp_amounts row per hospital, so
-- count(*) is the distinct hospital count).
all_stats as (
    select
        service_code_key, clean_setting, clean_billing_class,
        modifier_signature, amount_kind,
        count(*) as peer_hospital_count_all,
        median(hospital_amount) as market_median_all,
        quantile_cont(hospital_amount, 0.1) as market_p10_all,
        quantile_cont(hospital_amount, 0.9) as market_p90_all
    from hosp_amounts
    group by 1, 2, 3, 4, 5
),

state_stats as (
    select
        service_code_key, clean_setting, clean_billing_class,
        modifier_signature, amount_kind, canonical_state,
        count(*) as peer_hospital_count_state,
        median(hospital_amount) as market_median_state
    from hosp_amounts
    group by 1, 2, 3, 4, 5, 6
),

type_stats as (
    select
        service_code_key, clean_setting, clean_billing_class,
        modifier_signature, amount_kind, hospital_type,
        count(*) as peer_hospital_count_type,
        median(hospital_amount) as market_median_type
    from hosp_amounts
    group by 1, 2, 3, 4, 5, 6
),

system_stats as (
    select
        service_code_key, clean_setting, clean_billing_class,
        modifier_signature, amount_kind, health_system,
        count(*) as peer_hospital_count_system,
        median(hospital_amount) as market_median_system
    from hosp_amounts
    group by 1, 2, 3, 4, 5, 6
)

select
    r.hospital_id,
    r.service_code_key,
    r.clean_setting,
    r.clean_billing_class,
    r.modifier_signature,
    r.amount_kind,
    r.canonical_state,
    r.hospital_type,
    r.health_system,
    'tier_2_context_aligned' as comparison_tier,
    r.hospital_amount,

    -- all-market peer group
    a.peer_hospital_count_all,
    case when a.peer_hospital_count_all >= 3 then a.market_median_all end
        as market_median_all,
    case when a.peer_hospital_count_all >= 3 then a.market_p10_all end
        as market_p10_all,
    case when a.peer_hospital_count_all >= 3 then a.market_p90_all end
        as market_p90_all,
    case when a.peer_hospital_count_all >= 3 then r.amount_pct_rank_all end
        as amount_pct_rank_all,
    case
        when a.peer_hospital_count_all >= 3
        then r.hospital_amount - a.market_median_all
    end as delta_from_market_median_all,
    case
        when a.peer_hospital_count_all >= 3 and a.market_median_all <> 0
        then (r.hospital_amount - a.market_median_all) / a.market_median_all
    end as pct_delta_from_market_median_all,

    -- same-state peer group
    st.peer_hospital_count_state,
    case when st.peer_hospital_count_state >= 3 then st.market_median_state end
        as market_median_state,
    case when st.peer_hospital_count_state >= 3 then r.amount_pct_rank_state end
        as amount_pct_rank_state,
    case
        when st.peer_hospital_count_state >= 3
        then r.hospital_amount - st.market_median_state
    end as delta_from_market_median_state,

    -- same hospital_type peer group
    ty.peer_hospital_count_type,
    case when ty.peer_hospital_count_type >= 3 then ty.market_median_type end
        as market_median_type,
    case when ty.peer_hospital_count_type >= 3 then r.amount_pct_rank_type end
        as amount_pct_rank_type,
    case
        when ty.peer_hospital_count_type >= 3
        then r.hospital_amount - ty.market_median_type
    end as delta_from_market_median_type,

    -- same health_system peer group
    sy.peer_hospital_count_system,
    case when sy.peer_hospital_count_system >= 3 then sy.market_median_system end
        as market_median_system,
    case when sy.peer_hospital_count_system >= 3 then r.amount_pct_rank_system end
        as amount_pct_rank_system,
    case
        when sy.peer_hospital_count_system >= 3
        then r.hospital_amount - sy.market_median_system
    end as delta_from_market_median_system
from ranked as r
left join all_stats as a
    on r.service_code_key = a.service_code_key
    and r.clean_setting = a.clean_setting
    and r.clean_billing_class = a.clean_billing_class
    and r.modifier_signature = a.modifier_signature
    and r.amount_kind = a.amount_kind
left join state_stats as st
    on r.service_code_key = st.service_code_key
    and r.clean_setting = st.clean_setting
    and r.clean_billing_class = st.clean_billing_class
    and r.modifier_signature = st.modifier_signature
    and r.amount_kind = st.amount_kind
    and r.canonical_state is not distinct from st.canonical_state
left join type_stats as ty
    on r.service_code_key = ty.service_code_key
    and r.clean_setting = ty.clean_setting
    and r.clean_billing_class = ty.clean_billing_class
    and r.modifier_signature = ty.modifier_signature
    and r.amount_kind = ty.amount_kind
    and r.hospital_type is not distinct from ty.hospital_type
left join system_stats as sy
    on r.service_code_key = sy.service_code_key
    and r.clean_setting = sy.clean_setting
    and r.clean_billing_class = sy.clean_billing_class
    and r.modifier_signature = sy.modifier_signature
    and r.amount_kind = sy.amount_kind
    and r.health_system is not distinct from sy.health_system
