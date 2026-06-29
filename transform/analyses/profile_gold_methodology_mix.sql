-- Profiling: how payer-negotiated rates are expressed.
-- A negotiated rate may be a dollar amount, a percentage of charges, or a
-- contractual algorithm; only dollars are directly price-rankable. Counts come
-- from the coverage scorecard amount-kind tallies over current snapshots.
with cov as (
    select *
    from {{ ref('gld_score__snapshot_coverage_scorecard') }}
    where is_current_snapshot = true
),

totals as (
    select
        sum(obs_negotiated_dollar) as negotiated_dollar,
        sum(obs_negotiated_percentage) as negotiated_percentage,
        sum(obs_negotiated_algorithm) as negotiated_algorithm
    from cov
),

unpivoted as (
    select 'negotiated_dollar' as methodology, negotiated_dollar as n,
        (negotiated_dollar + negotiated_percentage + negotiated_algorithm) as total from totals
    union all select 'negotiated_percentage', negotiated_percentage,
        (negotiated_dollar + negotiated_percentage + negotiated_algorithm) from totals
    union all select 'negotiated_algorithm', negotiated_algorithm,
        (negotiated_dollar + negotiated_percentage + negotiated_algorithm) from totals
)

select
    methodology,
    n as observations,
    round(n / nullif(total, 0)::double, 4) as share
from unpivoted
order by observations desc
