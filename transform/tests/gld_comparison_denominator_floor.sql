-- Semantic guard (plan §10.4): published peer percentile/median columns may not
-- appear below the 3-hospital denominator floor (decision 0017). If any market
-- stat is non-null, peer_hospital_count must be >= 3.
select *
from {{ ref('gld__service_price_comparison_current') }}
where coalesce(peer_hospital_count, 0) < 3
    and (
        market_median_amount is not null
        or market_p10_amount is not null
        or market_p90_amount is not null
        or amount_pct_rank is not null
        or delta_from_market_median is not null
        or pct_delta_from_market_median is not null
    )
