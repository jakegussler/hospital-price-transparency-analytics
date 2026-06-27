-- Profiling: three-hospital denominator reality.
-- Of the (service_code_key + context + amount_kind) cohorts in the price summary,
-- how many actually clear the 3-hospital floor and can publish percentiles?
select
    amount_kind,
    count(*) as cohorts,
    sum((hospital_count >= 3)::int) as cohorts_meeting_floor,
    round(sum((hospital_count >= 3)::int) / count(*)::double, 4)
        as pct_cohorts_meeting_floor,
    max(hospital_count) as max_hospitals_in_a_cohort
from {{ ref('gld__service_price_summary') }}
group by 1
order by 1
