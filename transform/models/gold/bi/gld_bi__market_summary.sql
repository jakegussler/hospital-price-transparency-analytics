-- gld_bi__market_summary
--
-- One-row corpus-level headline summary for public BI landing pages.
-- Grain: exactly one row (summary_id = 'current_corpus').
--
-- Exists so dashboards get corpus KPIs with DISTINCT-COUNT semantics instead of
-- summing per-hospital counts from gld_bi__hospital_overview (which
-- double-counts services and payers shared across hospitals). All aggregation
-- happens here in dbt; Evidence page SQL reads the row as-is.

with hospitals as (
    select *
    from {{ ref('gld_bi__hospital_overview') }}
),

services as (
    select *
    from {{ ref('gld_bi__service_market_explorer') }}
),

payers as (
    select *
    from {{ ref('gld_bi__payer_contracting_explorer') }}
),

funnel_corpus as (
    select *
    from {{ ref('gld_bi__comparability_funnel') }}
    where scope_level = 'corpus'
),

hospital_agg as (
    select
        count(*) as hospital_count,
        count(distinct health_system) as health_system_count,
        coalesce(sum(current_snapshot_available::int), 0)
            as hospitals_with_current_snapshot,
        median(overall_readiness_score) as median_overall_readiness_score,
        coalesce(sum((data_confidence_band = 'high')::int), 0)
            as high_confidence_hospital_count,
        coalesce(sum((data_confidence_band = 'moderate')::int), 0)
            as moderate_confidence_hospital_count,
        coalesce(sum((data_confidence_band = 'limited')::int), 0)
            as limited_confidence_hospital_count,
        coalesce(sum((data_confidence_band = 'low')::int), 0)
            as low_confidence_hospital_count,
        min(published_last_updated_on) as earliest_published_last_updated_on,
        max(published_last_updated_on) as latest_published_last_updated_on
    from hospitals
),

service_agg as (
    select
        count(*) as service_context_count,
        coalesce(sum(meets_hospital_threshold::int), 0)
            as comparable_service_context_count,
        coalesce(sum((not meets_hospital_threshold)::int), 0)
            as thin_service_context_count,
        count(distinct service_code_key) as distinct_service_count,
        count(distinct case
            when meets_hospital_threshold then service_code_key
        end) as distinct_comparable_service_count,
        coalesce(sum(
            (meets_hospital_threshold and amount_kind = 'gross_charge')::int
        ), 0) as comparable_gross_charge_context_count,
        coalesce(sum(
            (meets_hospital_threshold and amount_kind = 'discounted_cash')::int
        ), 0) as comparable_discounted_cash_context_count,
        coalesce(sum(
            (meets_hospital_threshold and amount_kind = 'negotiated_dollar')::int
        ), 0) as comparable_negotiated_dollar_context_count
    from services
),

payer_agg as (
    select
        count(distinct canonical_payer_id) as matched_payer_count
    from payers
),

funnel_agg as (
    select
        coalesce(max(case
            when stage_code = 'published_rows' then row_count
        end), 0) as published_row_count,
        coalesce(max(case
            when stage_code = 'code_comparable_rows' then row_count
        end), 0) as code_comparable_row_count,
        coalesce(max(case
            when stage_code = 'context_aligned_rows' then row_count
        end), 0) as context_aligned_row_count,
        coalesce(max(case
            when stage_code = 'rankable_dollar_rows' then row_count
        end), 0) as rankable_dollar_row_count,
        coalesce(max(case
            when stage_code = 'meets_floor_rows' then row_count
        end), 0) as meets_floor_row_count
    from funnel_corpus
)

select
    'current_corpus' as summary_id,

    h.hospital_count,
    h.health_system_count,
    h.hospitals_with_current_snapshot,
    h.median_overall_readiness_score,
    h.high_confidence_hospital_count,
    h.moderate_confidence_hospital_count,
    h.limited_confidence_hospital_count,
    h.low_confidence_hospital_count,
    h.earliest_published_last_updated_on,
    h.latest_published_last_updated_on,

    s.service_context_count,
    s.comparable_service_context_count,
    s.thin_service_context_count,
    s.distinct_service_count,
    s.distinct_comparable_service_count,
    s.comparable_gross_charge_context_count,
    s.comparable_discounted_cash_context_count,
    s.comparable_negotiated_dollar_context_count,

    p.matched_payer_count,

    f.published_row_count,
    f.code_comparable_row_count,
    f.context_aligned_row_count,
    f.rankable_dollar_row_count,
    f.meets_floor_row_count,
    f.rankable_dollar_row_count / nullif(f.published_row_count, 0)::double
        as rankable_row_share,
    f.meets_floor_row_count / nullif(f.published_row_count, 0)::double
        as meets_floor_row_share
from hospital_agg as h
cross join service_agg as s
cross join payer_agg as p
cross join funnel_agg as f
