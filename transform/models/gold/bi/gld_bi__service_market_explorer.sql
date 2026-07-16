-- gld_bi__service_market_explorer
--
-- BI model for service-market exploration.
-- Grain: one row per exact comparison context (service_context_key) from
-- gld_mart__service_price_summary — service / setting / billing class /
-- modifiers / amount kind / comparison_methodology / drug unit context.
-- Adds display labels, threshold flags, spread measures, and trust/status fields
-- so dashboards can select/filter without re-implementing Gold rules.
--
-- Decision 0021: every price statistic here is HOSPITAL-WEIGHTED (one
-- representative amount per hospital) and METHODOLOGY-SEPARATED (per-diem daily
-- rates never share a distribution with case rates or fee schedules).
-- service_context_url_slug is the durable public link target for the exact
-- context.

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
),

labeled as (
    select
        s.service_context_key,
        s.service_code_key,
        sc.canonical_code_system,
        sc.match_code,
        {{ hpt_service_url_slug('sc.canonical_code_system', 'sc.match_code') }}
            as service_url_slug,
        upper(sc.canonical_code_system) || ' ' || sc.match_code as service_display_code,
        -- 'Description not available' (not 'Undescribed service'): for licensed
        -- code systems (CPT/CDT) the description exists but cannot be republished;
        -- description_availability carries the reason.
        coalesce(sc.code_description, 'Description not available') as service_display_name,
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
        {{ hpt_description_availability('sc.has_code_description', 'sc.canonical_code_system') }}
            as description_availability,
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
        s.comparison_methodology,
        {{ hpt_comparison_methodology_display_label('s.comparison_methodology') }}
            as comparison_methodology_display_label,
        s.canonical_drug_unit_type,

        s.observation_count,
        s.contract_count,
        s.reporting_hospital_count,
        s.hospital_count,
        s.excluded_hospital_count,
        s.ambiguous_contract_count,
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
        s.outlier_hospital_count,

        -- 'insufficient_denominator' is the BI representation of the cohort-grain
        -- below_min_hospital_denominator blocker (decision 0017, amended by 0021:
        -- hospital_count counts hospitals with a VALID representative). This is
        -- the canonical thin-cohort signal; gld_bi__comparison_blocker_summary
        -- covers only the 10 row-grain blockers and intentionally omits this one.
        case
            when not s.meets_hospital_threshold then 'insufficient_denominator'
            when sc.has_code_description then 'described_comparable'
            else 'code_only_comparable'
        end as comparison_status,
        -- comparison_confidence_band describes how solid THIS SERVICE CONTEXT's
        -- cross-hospital comparison is (cohort size + description availability).
        -- Deliberately named differently from
        -- gld_bi__hospital_overview.data_confidence_band (readiness-score derived);
        -- the two must never share the ambiguous name "trust_band" in a public
        -- artifact.
        case
            when not s.meets_hospital_threshold then 'low'
            when s.hospital_count >= 10 and sc.has_code_description then 'high'
            when s.hospital_count >= 5 then 'moderate'
            else 'limited'
        end as comparison_confidence_band,
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
)

select
    *,
    {{ hpt_service_context_url_slug(
        'service_url_slug', 'amount_kind', 'comparison_methodology',
        'service_context_key'
    ) }} as service_context_url_slug
from labeled
