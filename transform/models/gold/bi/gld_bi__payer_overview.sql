-- gld_bi__payer_overview
--
-- BI presentation surface for payer index cards and payer profile headers.
-- Grain: one row per canonical_payer_id appearing in the matched-payer
-- contracting explorer. Aggregates that mart with distinct-count semantics so
-- pages do not re-aggregate the large context-grain explorer at render time.
--
-- Only matched payers appear here by construction (unmatched identities never
-- enter gld_mart__payer_service_benchmarks). Cash-comparison and position-band
-- counts reuse the explorer's published bands; no new comparability logic.

with contexts as (
    select *
    from {{ ref('gld_bi__payer_contracting_explorer') }}
),

aggregated as (
    select
        canonical_payer_id,
        any_value(payer_display_name) as payer_display_name,
        any_value(payer_parent_name) as payer_parent_name,
        any_value(payer_type) as payer_type,

        count(distinct hospital_id) as hospital_count,
        count(distinct service_code_key) as service_count,
        count(*) as contract_context_count,
        coalesce(sum((coalesce(payer_hospital_count, 0) >= 3)::int), 0)
            as contexts_meeting_payer_floor,

        coalesce(sum((contract_position_band = 'well_below_payer_market')::int), 0)
            as contexts_well_below_payer_market,
        coalesce(sum((contract_position_band = 'below_payer_market')::int), 0)
            as contexts_below_payer_market,
        coalesce(sum((contract_position_band = 'near_payer_market')::int), 0)
            as contexts_near_payer_market,
        coalesce(sum((contract_position_band = 'above_payer_market')::int), 0)
            as contexts_above_payer_market,
        coalesce(sum((contract_position_band = 'well_above_payer_market')::int), 0)
            as contexts_well_above_payer_market,

        -- Decision 0021: only methodology-COMPATIBLE comparisons count as
        -- cash-available; per-diem-incompatible and ambiguous contexts are
        -- surfaced separately, never as below/equal/above cash.
        coalesce(sum((cash_comparison_band in
            ('below_cash', 'equal_to_cash', 'above_cash'))::int), 0)
            as cash_available_context_count,
        coalesce(sum((cash_comparison_band = 'below_cash')::int), 0)
            as below_cash_context_count,
        coalesce(sum((cash_comparison_band = 'equal_to_cash')::int), 0)
            as equal_to_cash_context_count,
        coalesce(sum((cash_comparison_band = 'above_cash')::int), 0)
            as above_cash_context_count,
        coalesce(sum((cash_comparison_band = 'per_diem_incompatible')::int), 0)
            as cash_incompatible_context_count,
        coalesce(sum((cash_comparison_band = 'ambiguous_negotiated_context')::int), 0)
            as ambiguous_context_count
    from contexts
    group by canonical_payer_id
)

select
    canonical_payer_id,
    payer_display_name,
    payer_parent_name,
    payer_type,
    hospital_count,
    service_count,
    contract_context_count,
    contexts_meeting_payer_floor,
    contexts_well_below_payer_market,
    contexts_below_payer_market,
    contexts_near_payer_market,
    contexts_above_payer_market,
    contexts_well_above_payer_market,
    cash_available_context_count,
    below_cash_context_count,
    equal_to_cash_context_count,
    above_cash_context_count,
    cash_incompatible_context_count,
    ambiguous_context_count,
    above_cash_context_count / nullif(cash_available_context_count, 0)::double
        as share_above_cash
from aggregated
