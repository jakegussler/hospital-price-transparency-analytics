-- Semantic guard (plan §10.4): no non-dollar amount may sit in the price-ranking
-- subset. Every is_price_ranking_row must be a usd, rankable amount.
select *
from {{ ref('gld__service_price_comparison_current') }}
where is_price_ranking_row = true
    and (amount_unit <> 'usd' or is_price_rankable = false)
