-- Profiling: amount-kind sparsity by source format.
-- Cash vs negotiated-dollar (and the comparable/derived split) coverage, to see
-- which formats actually carry rankable dollars.
select
    source_format,
    count(*) as observations,
    sum((amount_kind = 'gross_charge')::int) as gross_charge_obs,
    sum((amount_kind = 'discounted_cash')::int) as discounted_cash_obs,
    sum((amount_kind = 'negotiated_dollar')::int) as negotiated_dollar_obs,
    sum((
        amount_kind = 'negotiated_dollar'
        and amount_comparability_tier = 'comparable_dollar'
    )::int) as comparable_dollar_obs,
    sum((
        amount_kind = 'negotiated_dollar'
        and amount_comparability_tier = 'derived_dollar'
    )::int) as derived_dollar_obs,
    sum((amount_kind = 'negotiated_percentage')::int) as negotiated_percentage_obs,
    sum((amount_kind = 'negotiated_algorithm')::int) as negotiated_algorithm_obs
from {{ ref('gld_fct__rate_observations') }}
group by 1
order by 1
