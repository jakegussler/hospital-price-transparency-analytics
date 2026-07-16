-- gld_bi__payer_contracting_explorer
--
-- BI presentation surface for payer contracting exploration.
-- Grain: one row per (canonical_payer_id, hospital_id, service_context_key)
-- from gld_mart__payer_service_benchmarks, enriched with labels and
-- contracting bands.
--
-- Decision 0021: negotiated_dollar is the payer-hospital representative
-- (deduplicated contract votes), the payer market is hospital-weighted and
-- methodology-separated, and cash comparisons carry cash_comparison_status —
-- a per-diem daily rate is never labeled above or below a cash amount.

with benchmarks as (
    select *
    from {{ ref('gld_mart__payer_service_benchmarks') }}
),

hospitals as (
    select *
    from {{ ref('gld_dim__hospital') }}
),

service_codes as (
    select *
    from {{ ref('gld_dim__service_code') }}
),

modifiers as (
    select *
    from {{ ref('gld_dim__modifier_signature') }}
),

labeled as (
    select
        b.canonical_payer_id,
        b.canonical_payer_name as payer_display_name,
        b.payer_parent_name,
        b.payer_type,

        b.hospital_id,
        h.canonical_hospital_name as hospital_display_name,
        h.health_system,
        h.hospital_type,
        h.canonical_state,
        h.canonical_state_name,

        b.service_context_key,
        b.service_code_key,
        sc.canonical_code_system,
        sc.match_code,
        {{ hpt_service_url_slug('sc.canonical_code_system', 'sc.match_code') }}
            as service_url_slug,
        upper(sc.canonical_code_system) || ' ' || sc.match_code as service_display_code,
        coalesce(sc.code_description, 'Description not available') as service_display_name,
        upper(sc.canonical_code_system) || ' ' || sc.match_code
            || case
                when sc.code_description is not null then ' - ' || sc.code_description
                else ''
            end as service_display_label,
        sc.has_code_description,
        {{ hpt_description_availability('sc.has_code_description', 'sc.canonical_code_system') }}
            as description_availability,
        sc.relative_weight,
        sc.ms_drg_mdc,
        sc.ms_drg_type,

        b.clean_setting,
        b.clean_billing_class,
        b.modifier_signature,
        coalesce(m.modifier_label, 'Unknown modifier context') as modifier_display_label,
        b.amount_kind,
        b.comparison_methodology,
        {{ hpt_comparison_methodology_display_label('b.comparison_methodology') }}
            as comparison_methodology_display_label,
        b.canonical_drug_unit_type,
        b.market_segment,

        b.negotiated_dollar,
        b.source_contract_count,
        b.valid_contract_count,
        b.ambiguous_contract_count,
        b.cash_comparison_status,
        b.hospital_cash_amount,
        b.delta_from_hospital_cash,
        b.pct_delta_from_hospital_cash,
        b.payer_hospital_count,
        b.payer_market_median_negotiated,
        b.delta_from_payer_market_median,
        b.pct_delta_from_payer_market_median,
        b.context_hospital_count,
        b.payer_match_coverage_rate,

        case
            when b.negotiated_dollar is null then 'ambiguous_negotiated_context'
            when coalesce(b.payer_hospital_count, 0) < 3 then 'insufficient_denominator'
            when b.pct_delta_from_payer_market_median <= -0.25 then 'well_below_payer_market'
            when b.pct_delta_from_payer_market_median <= -0.10 then 'below_payer_market'
            when b.pct_delta_from_payer_market_median >= 0.25 then 'well_above_payer_market'
            when b.pct_delta_from_payer_market_median >= 0.10 then 'above_payer_market'
            else 'near_payer_market'
        end as contract_position_band,
        -- Above/below/equal labels exist ONLY where the comparison is
        -- methodology-compatible (cash_comparison_status = 'comparable');
        -- incompatible or ambiguous contexts carry their status instead of a
        -- direction (decision 0021).
        case
            when b.cash_comparison_status <> 'comparable' then b.cash_comparison_status
            when b.negotiated_dollar < b.hospital_cash_amount then 'below_cash'
            when b.negotiated_dollar > b.hospital_cash_amount then 'above_cash'
            else 'equal_to_cash'
        end as cash_comparison_band
    from benchmarks as b
    left join hospitals as h
        on b.hospital_id = h.hospital_id
    left join service_codes as sc
        on b.service_code_key = sc.service_code_key
    left join modifiers as m
        on b.modifier_signature = m.modifier_signature
)

select
    *,
    {{ hpt_service_context_url_slug(
        'service_url_slug', 'amount_kind', 'comparison_methodology',
        'service_context_key'
    ) }} as service_context_url_slug
from labeled
