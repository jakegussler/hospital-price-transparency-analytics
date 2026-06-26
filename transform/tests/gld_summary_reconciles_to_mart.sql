-- Reconciliation (plan §10.5): the summary is the price-ranking subset of
-- gld__service_price_comparison_current grouped to the service context, so the sum
-- of its observation_count must equal the count of is_price_ranking_row = true rows
-- in the comparison mart. Any drift fails.
with summary_total as (
    select coalesce(sum(observation_count), 0) as n
    from {{ ref('gld__service_price_summary') }}
),

mart_total as (
    select count(*) as n
    from {{ ref('gld__service_price_comparison_current') }}
    where is_price_ranking_row = true
)

select
    summary_total.n as summary_observation_total,
    mart_total.n as mart_rankable_row_total
from summary_total
cross join mart_total
where summary_total.n <> mart_total.n
