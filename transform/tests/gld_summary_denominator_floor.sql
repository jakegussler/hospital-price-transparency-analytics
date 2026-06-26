-- Semantic guard (plan §10.4): gld__service_price_summary must not publish any
-- distribution statistic below the 3-hospital denominator floor (decision 0017).
-- If any percentile/spread/IQR/outlier column is non-null, hospital_count >= 3.
select *
from {{ ref('gld__service_price_summary') }}
where hospital_count < 3
    and (
        min_amount is not null
        or p10_amount is not null
        or median_amount is not null
        or p90_amount is not null
        or max_amount is not null
        or iqr_amount is not null
        or spread_ratio_p90_to_p10 is not null
        or outlier_observation_count is not null
    )
