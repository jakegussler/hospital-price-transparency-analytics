-- gld_bi__featured_services
--
-- Rule-selected small service list for public reporting defaults.
-- Grain: one row per service/context/amount_kind, selected from
-- gld_bi__service_market_explorer. This is intentionally not a manual service
-- master: it surfaces described, comparable, high-coverage examples that are
-- useful as dashboard defaults while leaving canonical service grouping out of
-- scope.

with candidates as (
    select
        *,
        row_number() over (
            order by
                has_code_description desc,
                hospital_count desc,
                coalesce(spread_ratio_p90_to_p10, 0) desc,
                observation_count desc,
                service_display_code
        ) as featured_rank
    from {{ ref('gld_bi__service_market_explorer') }}
    where meets_hospital_threshold = true
        and has_code_description = true
        and amount_kind in ('negotiated_dollar', 'discounted_cash', 'gross_charge')
)

select
    featured_rank,
    case
        when spread_ratio_p90_to_p10 >= 3 then 'wide_price_variation'
        when hospital_count >= 10 then 'broad_hospital_coverage'
        else 'described_comparable_service'
    end as featured_reason,
    service_code_key,
    canonical_code_system,
    match_code,
    service_url_slug,
    service_display_code,
    service_display_name,
    service_display_label,
    code_description,
    code_description_edition,
    clean_setting,
    clean_billing_class,
    modifier_signature,
    modifier_display_label,
    amount_kind,
    observation_count,
    hospital_count,
    payer_count,
    median_amount,
    p10_amount,
    p90_amount,
    spread_amount_p90_to_p10,
    spread_ratio_p90_to_p10,
    comparison_confidence_band,
    variation_band
from candidates
where featured_rank <= 30
