-- Semantic guard (plan §10.4): the *_current mart must contain only current
-- snapshots. Zero rows may carry is_current_snapshot = false.
select *
from {{ ref('gld_mart__service_price_comparison_current') }}
where is_current_snapshot = false
