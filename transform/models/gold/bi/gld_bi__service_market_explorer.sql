-- gld_bi__service_market_explorer
--
-- BI model for service-market exploration.
-- Grain: one row per service/context/amount_kind from gld_mart__service_price_summary.
-- Adds display labels, threshold flags, spread measures, and trust/status fields
-- so dashboards can select/filter without re-implementing Gold rules.

with summary as (
    select *
    from {{ ref('gld_mart__service_price_summary') }}
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
    s.service_code_key,
    sc.canonical_code_system,
    sc.match_code,
    upper(sc.canonical_code_system) || ' ' || sc.match_code as service_display_code,
    coalesce(sc.code_description, 'Undescribed service') as service_display_name,
    upper(sc.canonical_code_system) || ' ' || sc.match_code
        || case
            when sc.code_description is not null then ' - ' || sc.code_description
            else ''
        end as service_display_label,
    sc.code_description,
    sc.code_description_edition,
    sc.code_description_source,
    sc.code_description_license,
    sc.has_code_description,
    sc.relative_weight,
    sc.ms_drg_mdc,
    sc.ms_drg_type,

    s.clean_setting,
    s.clean_billing_class,
    s.modifier_signature,
    coalesce(m.modifier_label, 'Unknown modifier context') as modifier_display_label,
    m.modifier_count,
    m.has_pro_tech_split_modifier,
    s.amount_kind,

    s.observation_count,
    s.hospital_count,
    s.payer_count,
    s.meets_hospital_threshold,
    s.market_coverage_rate,

    s.min_amount,
    s.p10_amount,
    s.median_amount,
    s.p90_amount,
    s.max_amount,
    case
        when s.meets_hospital_threshold then s.p90_amount - s.p10_amount
    end as spread_amount_p90_to_p10,
    s.spread_ratio_p90_to_p10,
    s.iqr_amount,
    s.outlier_observation_count,

    case
        when not s.meets_hospital_threshold then 'insufficient_denominator'
        when sc.has_code_description then 'described_comparable'
        else 'code_only_comparable'
    end as comparison_status,
    case
        when not s.meets_hospital_threshold then 'low_trust'
        when s.hospital_count >= 10 and sc.has_code_description then 'high_trust'
        when s.hospital_count >= 5 then 'moderate_trust'
        else 'limited_trust'
    end as trust_band,
    case
        when s.meets_hospital_threshold
            and s.spread_ratio_p90_to_p10 >= 3 then 'very_high_variation'
        when s.meets_hospital_threshold
            and s.spread_ratio_p90_to_p10 >= 2 then 'high_variation'
        when s.meets_hospital_threshold then 'moderate_variation'
        else 'not_ranked'
    end as variation_band
from summary as s
left join service_codes as sc
    on s.service_code_key = sc.service_code_key
left join modifiers as m
    on s.modifier_signature = m.modifier_signature
