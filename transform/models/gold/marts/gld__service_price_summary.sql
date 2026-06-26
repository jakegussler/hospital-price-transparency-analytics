-- gld__service_price_summary (plan §7.2)
--
-- Aggregate variation/distribution model. Grain: one row per
-- (service_code_key, clean_setting, clean_billing_class, modifier_signature,
-- amount_kind). Built from the price-ranking subset of
-- gld__service_price_comparison_current (is_price_ranking_row = true), so it
-- reconciles to that mart by construction and inherits its current-only,
-- tier_2 + dollar-rankable inclusion.
--
-- Denominator rule (decision 0017): percentile/median/spread/IQR/outlier columns
-- are SUPPRESSED (nulled) below the 3-hospital threshold; the denominator counts
-- (observation/hospital/payer) always stay beside them and meets_hospital_threshold
-- flags the row. Outliers are flagged (robust 1.5×IQR fences), never winsorized
-- (open question §14.3 — flag-only in Phase 1).
--
-- Cross-snapshot aggregate → full-refresh table (marts config) reading the
-- comparison mart through plain ref().

with base as (
    select
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        hospital_id,
        canonical_payer_id,
        amount_value
    from {{ ref('gld__service_price_comparison_current') }}
    where is_price_ranking_row = true
),

-- Total distinct hospitals reporting any rankable price (market_coverage_rate
-- denominator).
market_size as (
    select count(distinct hospital_id) as total_rankable_hospitals
    from base
),

group_stats as (
    select
        service_code_key,
        clean_setting,
        clean_billing_class,
        modifier_signature,
        amount_kind,
        count(*) as observation_count,
        count(distinct hospital_id) as hospital_count,
        count(distinct case
            when canonical_payer_id is not null
                and canonical_payer_id <> '<unmatched>'
            then canonical_payer_id
        end) as payer_count,
        min(amount_value) as min_amount,
        quantile_cont(amount_value, 0.1) as p10_amount,
        quantile_cont(amount_value, 0.25) as p25_amount,
        median(amount_value) as median_amount,
        quantile_cont(amount_value, 0.75) as p75_amount,
        quantile_cont(amount_value, 0.9) as p90_amount,
        max(amount_value) as max_amount
    from base
    group by 1, 2, 3, 4, 5
),

-- Robust IQR outlier flag per group, counted back to the group.
outliers as (
    select
        b.service_code_key,
        b.clean_setting,
        b.clean_billing_class,
        b.modifier_signature,
        b.amount_kind,
        sum((
            b.amount_value < g.p25_amount - 1.5 * (g.p75_amount - g.p25_amount)
            or b.amount_value > g.p75_amount + 1.5 * (g.p75_amount - g.p25_amount)
        )::int) as outlier_observation_count
    from base as b
    join group_stats as g
        on b.service_code_key = g.service_code_key
        and b.clean_setting = g.clean_setting
        and b.clean_billing_class = g.clean_billing_class
        and b.modifier_signature = g.modifier_signature
        and b.amount_kind = g.amount_kind
    group by 1, 2, 3, 4, 5
)

select
    g.service_code_key,
    g.clean_setting,
    g.clean_billing_class,
    g.modifier_signature,
    g.amount_kind,

    -- denominators (always published)
    g.observation_count,
    g.hospital_count,
    g.payer_count,
    (g.hospital_count >= 3) as meets_hospital_threshold,
    g.hospital_count / nullif(m.total_rankable_hospitals, 0)::double
        as market_coverage_rate,

    -- distribution stats (suppressed below the 3-hospital floor)
    case when g.hospital_count >= 3 then g.min_amount end as min_amount,
    case when g.hospital_count >= 3 then g.p10_amount end as p10_amount,
    case when g.hospital_count >= 3 then g.median_amount end as median_amount,
    case when g.hospital_count >= 3 then g.p90_amount end as p90_amount,
    case when g.hospital_count >= 3 then g.max_amount end as max_amount,
    case
        when g.hospital_count >= 3 then g.p75_amount - g.p25_amount
    end as iqr_amount,
    case
        when g.hospital_count >= 3 and g.p10_amount <> 0
        then g.p90_amount / g.p10_amount
    end as spread_ratio_p90_to_p10,
    case
        when g.hospital_count >= 3 then o.outlier_observation_count
    end as outlier_observation_count
from group_stats as g
cross join market_size as m
left join outliers as o
    on g.service_code_key = o.service_code_key
    and g.clean_setting = o.clean_setting
    and g.clean_billing_class = o.clean_billing_class
    and g.modifier_signature = o.modifier_signature
    and g.amount_kind = o.amount_kind
