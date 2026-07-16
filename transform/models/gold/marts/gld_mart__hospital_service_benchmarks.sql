-- gld_mart__hospital_service_benchmarks
--
-- User question: "For a given service + context, how does THIS hospital's price
-- compare to the market and to its peer groups?"
--
-- Grain: one row per (hospital_id, service_context_key) = hospital × exact
-- comparison context (service_code_key, clean_setting, clean_billing_class,
-- modifier_signature, amount_kind, comparison_methodology,
-- canonical_drug_unit_type).
--
-- Decision 0021: the hospital's representative amount comes from the shared
-- gld_int__hospital_service_amounts layer (one vote per hospital; negotiated
-- dollars are medians of valid contract representatives, so repeated contract
-- rows cannot add weight), and every peer partition includes the methodology-
-- separated exact context. The service summary reads the same representative
-- layer, so its percentiles and these benchmarks reconcile by construction.
-- Hospitals whose context could not be represented safely (all contracts
-- ambiguous) carry no representative and are excluded here; they remain visible
-- in the comparison mart and the summary's excluded_hospital_count.
--
-- Market comparison is published for four peer groups — all, same state, same
-- hospital_type, same health_system — each gated by its own 3-hospital
-- denominator (decision 0017): below the floor, that peer group's stats are
-- null but the row and its hospital_amount still appear.
--
-- Cross-snapshot aggregate → full-refresh table (marts config).

with hosp_amounts as (
    select
        h.hospital_id,
        dh.canonical_state,
        dh.hospital_type,
        dh.health_system,
        h.service_context_key,
        h.service_code_key,
        h.clean_setting,
        h.clean_billing_class,
        h.modifier_signature,
        h.amount_kind,
        h.comparison_methodology,
        h.canonical_drug_unit_type,
        h.hospital_amount,
        h.raw_observation_count,
        h.source_contract_count,
        h.valid_contract_count,
        h.ambiguous_contract_count
    from {{ ref('gld_int__hospital_service_amounts') }} as h
    left join {{ ref('gld_dim__hospital') }} as dh
        on h.hospital_id = dh.hospital_id
    where h.hospital_amount is not null
),

-- Per-hospital percentile rank within each peer group (one row per hospital in
-- hosp_amounts, so percent_rank is hospital-weighted by construction).
ranked as (
    select
        *,
        percent_rank() over (
            partition by service_context_key
            order by hospital_amount
        ) as amount_pct_rank_all,
        percent_rank() over (
            partition by service_context_key, canonical_state
            order by hospital_amount
        ) as amount_pct_rank_state,
        percent_rank() over (
            partition by service_context_key, hospital_type
            order by hospital_amount
        ) as amount_pct_rank_type,
        percent_rank() over (
            partition by service_context_key, health_system
            order by hospital_amount
        ) as amount_pct_rank_system
    from hosp_amounts
),

-- Peer-group medians + hospital counts (one hosp_amounts row per hospital, so
-- count(*) is the distinct hospital count).
all_stats as (
    select
        service_context_key,
        count(*) as peer_hospital_count_all,
        median(hospital_amount) as market_median_all,
        quantile_cont(hospital_amount, 0.1) as market_p10_all,
        quantile_cont(hospital_amount, 0.9) as market_p90_all
    from hosp_amounts
    group by 1
),

state_stats as (
    select
        service_context_key, canonical_state,
        count(*) as peer_hospital_count_state,
        median(hospital_amount) as market_median_state
    from hosp_amounts
    group by 1, 2
),

type_stats as (
    select
        service_context_key, hospital_type,
        count(*) as peer_hospital_count_type,
        median(hospital_amount) as market_median_type
    from hosp_amounts
    group by 1, 2
),

system_stats as (
    select
        service_context_key, health_system,
        count(*) as peer_hospital_count_system,
        median(hospital_amount) as market_median_system
    from hosp_amounts
    group by 1, 2
)

select
    r.hospital_id,
    r.service_context_key,
    r.service_code_key,
    r.clean_setting,
    r.clean_billing_class,
    r.modifier_signature,
    r.amount_kind,
    r.comparison_methodology,
    r.canonical_drug_unit_type,
    r.canonical_state,
    r.hospital_type,
    r.health_system,
    'tier_2_context_aligned' as comparison_tier,
    r.hospital_amount,

    -- contract-level diagnostics (null for gross/cash; no contract concept)
    r.raw_observation_count,
    r.source_contract_count,
    r.valid_contract_count,
    r.ambiguous_contract_count,

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
    on r.service_context_key = a.service_context_key
left join state_stats as st
    on r.service_context_key = st.service_context_key
    and r.canonical_state is not distinct from st.canonical_state
left join type_stats as ty
    on r.service_context_key = ty.service_context_key
    and r.hospital_type is not distinct from ty.hospital_type
left join system_stats as sy
    on r.service_context_key = sy.service_context_key
    and r.health_system is not distinct from sy.health_system
