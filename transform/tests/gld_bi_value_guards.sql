-- Semantic guards for the Gold BI presentation layer: rates stay in [0, 1],
-- counts are nonnegative, and threshold-gated market stats are not published
-- where their denominator is too thin.

select 'hospital_overview_rate_bounds' as failure_case
from {{ ref('gld_bi__hospital_overview') }}
where overall_readiness_score not between 0 and 1
    or freshness_score not between 0 and 1
    or code_coverage_score not between 0 and 1
    or amount_coverage_score not between 0 and 1
    or payer_mapping_score not between 0 and 1
    or comparison_readiness_score not between 0 and 1
    or coded_item_coverage_rate not between 0 and 1
    or dollar_observation_coverage_rate not between 0 and 1
    or payer_mapping_coverage_rate not between 0 and 1
    or benchmark_context_count < 0
    or payer_contract_context_count < 0

union all

select 'service_market_denominator_floor' as failure_case
from {{ ref('gld_bi__service_market_explorer') }}
where meets_hospital_threshold = false
    and (
        min_amount is not null
        or p10_amount is not null
        or median_amount is not null
        or p90_amount is not null
        or max_amount is not null
        or spread_amount_p90_to_p10 is not null
        or spread_ratio_p90_to_p10 is not null
        or iqr_amount is not null
        or outlier_observation_count is not null
    )

union all

select 'hospital_rankings_nonnegative_counts' as failure_case
from {{ ref('gld_bi__hospital_service_rankings') }}
where coalesce(peer_hospital_count_all, 0) < 0
    or coalesce(peer_hospital_count_state, 0) < 0
    or coalesce(peer_hospital_count_type, 0) < 0
    or coalesce(peer_hospital_count_system, 0) < 0

union all

select 'payer_contracting_rate_bounds' as failure_case
from {{ ref('gld_bi__payer_contracting_explorer') }}
where payer_match_coverage_rate not between 0 and 1
    or coalesce(payer_hospital_count, 0) < 0
    or coalesce(context_hospital_count, 0) < 0

union all

select 'blocker_summary_rate_bounds' as failure_case
from {{ ref('gld_bi__comparison_blocker_summary') }}
where blocked_row_share not between 0 and 1
    or blocked_row_count < 0
    or classified_row_count < 0

union all

select 'comparability_funnel_bounds' as failure_case
from {{ ref('gld_bi__comparability_funnel') }}
where row_count < 0
    or published_row_count < 0
    or share_of_published not between 0 and 1

union all

select 'market_summary_bounds' as failure_case
from {{ ref('gld_bi__market_summary') }}
where hospital_count < 0
    or hospitals_with_current_snapshot > hospital_count
    or median_overall_readiness_score not between 0 and 1
    or comparable_service_context_count + thin_service_context_count
        <> service_context_count
    or distinct_comparable_service_count > distinct_service_count
    or rankable_row_share not between 0 and 1
    or meets_floor_row_share not between 0 and 1
    or meets_floor_row_count > rankable_dollar_row_count

union all

select 'payer_overview_bounds' as failure_case
from {{ ref('gld_bi__payer_overview') }}
where hospital_count < 0
    or service_count < 0
    or contract_context_count < 0
    or contexts_meeting_payer_floor > contract_context_count
    or cash_available_context_count > contract_context_count
    or below_cash_context_count + equal_to_cash_context_count
        + above_cash_context_count <> cash_available_context_count
    or share_above_cash not between 0 and 1
