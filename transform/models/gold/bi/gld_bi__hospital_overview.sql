-- gld_bi__hospital_overview
--
-- BI presentation surface for hospital-level scorecards and profile cards.
-- Grain: one row per hospital_id, scoped to the current scored snapshot when
-- available. Joins display attributes, readiness scores, coverage measures, and
-- lightweight counts from benchmark marts so dashboard tools do not need to
-- repeat Gold business logic.

with scorecard as (
    select *
    from {{ ref('gld__hospital_transparency_scorecard') }}
),

snapshot_coverage as (
    select *
    from {{ ref('gld__snapshot_coverage_scorecard') }}
),

service_benchmark_counts as (
    select
        hospital_id,
        count(*) as benchmark_context_count,
        count(distinct service_code_key) as benchmark_service_count,
        count(distinct case
            when peer_hospital_count_all >= 3 then service_code_key
        end) as benchmark_services_meeting_floor
    from {{ ref('gld__hospital_service_benchmarks') }}
    group by hospital_id
),

payer_benchmark_counts as (
    select
        hospital_id,
        count(*) as payer_contract_context_count,
        count(distinct canonical_payer_id) as matched_payer_count,
        count(distinct service_code_key) as payer_contract_service_count
    from {{ ref('gld__payer_service_benchmarks') }}
    group by hospital_id
),

ranked as (
    select
        sc.*,
        dense_rank() over (
            order by sc.overall_readiness_score desc, sc.hospital_id
        ) as overall_readiness_rank,
        dense_rank() over (
            order by sc.comparison_readiness_score desc, sc.hospital_id
        ) as comparison_readiness_rank,
        dense_rank() over (
            order by sc.payer_mapping_score desc, sc.hospital_id
        ) as payer_mapping_rank
    from scorecard as sc
)

select
    r.hospital_id,
    r.canonical_hospital_name as hospital_display_name,
    r.canonical_state,
    r.hospital_type,
    r.health_system,
    h.canonical_state_name,
    h.canonical_census_region,
    h.canonical_census_division,
    h.expected_format,
    h.mrf_url,

    r.snapshot_id,
    r.current_snapshot_available,
    scov.is_current_snapshot,
    scov.published_last_updated_on,
    r.snapshot_age_days,
    r.freshness_bucket,

    r.overall_readiness_score,
    r.freshness_score,
    r.code_coverage_score,
    r.amount_coverage_score,
    r.payer_mapping_score,
    r.comparison_readiness_score,
    r.overall_readiness_rank,
    r.comparison_readiness_rank,
    r.payer_mapping_rank,
    case
        when r.overall_readiness_score >= 0.85 then 'high_trust'
        when r.overall_readiness_score >= 0.70 then 'moderate_trust'
        when r.overall_readiness_score >= 0.50 then 'limited_trust'
        else 'low_trust'
    end as trust_band,

    r.charge_item_count,
    scov.standard_charge_count,
    scov.payer_rate_count,
    r.observation_count,
    r.distinct_comparable_codes,
    coalesce(sbc.benchmark_context_count, 0) as benchmark_context_count,
    coalesce(sbc.benchmark_service_count, 0) as benchmark_service_count,
    coalesce(sbc.benchmark_services_meeting_floor, 0)
        as benchmark_services_meeting_floor,
    coalesce(pbc.payer_contract_context_count, 0) as payer_contract_context_count,
    coalesce(pbc.matched_payer_count, 0) as matched_payer_count,
    coalesce(pbc.payer_contract_service_count, 0) as payer_contract_service_count,

    r.coded_item_coverage_rate,
    r.dollar_observation_coverage_rate,
    scov.discounted_cash_coverage_rate,
    scov.negotiated_dollar_coverage_rate,
    r.payer_mapping_coverage_rate
from ranked as r
left join {{ ref('gld_dim__hospital') }} as h
    on r.hospital_id = h.hospital_id
left join snapshot_coverage as scov
    on r.snapshot_id = scov.snapshot_id
left join service_benchmark_counts as sbc
    on r.hospital_id = sbc.hospital_id
left join payer_benchmark_counts as pbc
    on r.hospital_id = pbc.hospital_id
