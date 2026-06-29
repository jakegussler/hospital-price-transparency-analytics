-- Semantic guard (plan §10.4): ratio metrics must null their denominator-zero
-- cases. pct_delta_from_market_median must be null whenever the market median is
-- zero (the divisor).
select *
from {{ ref('gld_mart__service_price_comparison_current') }}
where market_median_amount = 0
    and pct_delta_from_market_median is not null
