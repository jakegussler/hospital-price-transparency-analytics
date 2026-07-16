-- Weighting guard (decision 0021): a hospital has at most ONE percentile rank
-- per exact comparison context — every ranked row of one hospital/context shares
-- the hospital representative's rank. More than one distinct rank means an
-- observation-weighted rank leaked back in.
select
    hospital_id,
    service_context_key,
    count(distinct amount_pct_rank) as distinct_ranks
from {{ ref('gld_mart__service_price_comparison_current') }}
where amount_pct_rank is not null
group by 1, 2
having count(distinct amount_pct_rank) > 1

union all

-- Same rule for the payer-specific cut.
select
    hospital_id,
    service_context_key,
    count(distinct payer_amount_pct_rank) as distinct_ranks
from {{ ref('gld_mart__service_price_comparison_current') }}
where payer_amount_pct_rank is not null
group by 1, 2, canonical_payer_id
having count(distinct payer_amount_pct_rank) > 1
