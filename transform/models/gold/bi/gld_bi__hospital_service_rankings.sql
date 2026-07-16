-- gld_bi__hospital_service_rankings
--
-- BI presentation surface for hospital-vs-market service rankings.
-- Grain: one row per (hospital_id, service_context_key) from
-- gld_mart__hospital_service_benchmarks, enriched with labels and position bands.
--
-- Decision 0021: hospital_amount is the hospital's ONE representative amount
-- for the methodology-separated exact context, and every peer statistic is
-- hospital-weighted. service_context_url_slug is the durable public link
-- target, so hospital pages can link to the exact context they ranked.

with benchmarks as (
    select *
    from {{ ref('gld_mart__hospital_service_benchmarks') }}
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
    b.comparison_tier,

    b.hospital_amount,
    b.raw_observation_count,
    b.source_contract_count,
    b.valid_contract_count,
    b.ambiguous_contract_count,
    b.peer_hospital_count_all,
    b.market_median_all,
    b.market_p10_all,
    b.market_p90_all,
    b.amount_pct_rank_all,
    b.delta_from_market_median_all,
    b.pct_delta_from_market_median_all,

    b.peer_hospital_count_state,
    b.market_median_state,
    b.amount_pct_rank_state,
    b.delta_from_market_median_state,

    b.peer_hospital_count_type,
    b.market_median_type,
    b.amount_pct_rank_type,
    b.delta_from_market_median_type,

    b.peer_hospital_count_system,
    b.market_median_system,
    b.amount_pct_rank_system,
    b.delta_from_market_median_system,

    case
        when coalesce(b.peer_hospital_count_all, 0) < 3 then 'insufficient_denominator'
        when b.pct_delta_from_market_median_all <= -0.25
            or b.amount_pct_rank_all <= 0.10 then 'very_low'
        when b.pct_delta_from_market_median_all <= -0.10
            or b.amount_pct_rank_all <= 0.25 then 'low'
        when b.pct_delta_from_market_median_all >= 0.25
            or b.amount_pct_rank_all >= 0.90 then 'very_high'
        when b.pct_delta_from_market_median_all >= 0.10
            or b.amount_pct_rank_all >= 0.75 then 'high'
        else 'near_market'
    end as price_position_band,
    (
        coalesce(b.peer_hospital_count_all, 0) >= 3
        and (
            b.pct_delta_from_market_median_all >= 0.50
            or b.amount_pct_rank_all >= 0.90
        )
    ) as is_high_outlier,
    (
        coalesce(b.peer_hospital_count_all, 0) >= 3
        and (
            b.pct_delta_from_market_median_all <= -0.50
            or b.amount_pct_rank_all <= 0.10
        )
    ) as is_low_outlier
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
