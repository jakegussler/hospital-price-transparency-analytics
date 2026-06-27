-- Profiling: multi-code expansion factor.
-- How many distinct comparable code cohorts does each observation fan out to in
-- the bridge? This is the magnitude of the gld_bridge__rate_observation_code
-- fan-out the comparison mart absorbs.
with codes_per_obs as (
    select
        gold_rate_observation_id,
        count(distinct service_code_key) as comparable_codes
    from {{ ref('gld_bridge__rate_observation_code') }}
    where service_code_key is not null
    group by 1
)

select
    count(*) as observations_with_comparable_code,
    round(avg(comparable_codes), 3) as avg_comparable_codes_per_obs,
    quantile_cont(comparable_codes, 0.5) as median_comparable_codes_per_obs,
    max(comparable_codes) as max_comparable_codes_per_obs,
    sum((comparable_codes > 1)::int) as obs_with_multiple_comparable_codes
from codes_per_obs
