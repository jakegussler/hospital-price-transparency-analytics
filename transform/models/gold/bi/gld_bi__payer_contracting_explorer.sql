-- gld_bi__payer_contracting_explorer
--
-- BI presentation surface for payer contracting exploration.
-- Grain: one row per payer/hospital/service/context from
-- gld__payer_service_benchmarks, enriched with labels and contracting bands.

with benchmarks as (
    select *
    from {{ ref('gld__payer_service_benchmarks') }}
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
)

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

    b.service_code_key,
    sc.canonical_code_system,
    sc.match_code,
    upper(sc.canonical_code_system) || ' ' || sc.match_code as service_display_code,
    coalesce(sc.code_description, 'Undescribed service') as service_display_name,
    upper(sc.canonical_code_system) || ' ' || sc.match_code
        || case
            when sc.code_description is not null then ' - ' || sc.code_description
            else ''
        end as service_display_label,
    sc.has_code_description,
    sc.relative_weight,
    sc.ms_drg_mdc,
    sc.ms_drg_type,

    b.clean_setting,
    b.clean_billing_class,
    b.modifier_signature,
    coalesce(m.modifier_label, 'Unknown modifier context') as modifier_display_label,
    b.amount_kind,
    b.market_segment,

    b.negotiated_dollar,
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
        when coalesce(b.payer_hospital_count, 0) < 3 then 'insufficient_denominator'
        when b.pct_delta_from_payer_market_median <= -0.25 then 'well_below_payer_market'
        when b.pct_delta_from_payer_market_median <= -0.10 then 'below_payer_market'
        when b.pct_delta_from_payer_market_median >= 0.25 then 'well_above_payer_market'
        when b.pct_delta_from_payer_market_median >= 0.10 then 'above_payer_market'
        else 'near_payer_market'
    end as contract_position_band,
    case
        when b.hospital_cash_amount is null then 'cash_unavailable'
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
