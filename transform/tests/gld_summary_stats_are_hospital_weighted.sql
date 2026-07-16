-- Weighting guard (decision 0021): the summary's published P10 / median / P90
-- must EXACTLY equal an independent recomputation over one representative amount
-- per hospital (gld_int__hospital_service_amounts.hospital_amount). Any drift
-- means an observation-weighted (or otherwise wrong) statistic leaked back in —
-- the $1,947 per-diem repetition bug this framework exists to prevent.
with recomputed as (
    select
        service_context_key,
        count(hospital_amount) as hospital_count,
        quantile_cont(hospital_amount, 0.1) as p10_recomputed,
        median(hospital_amount) as median_recomputed,
        quantile_cont(hospital_amount, 0.9) as p90_recomputed
    from {{ ref('gld_int__hospital_service_amounts') }}
    group by 1
)

select
    s.service_context_key,
    s.p10_amount,
    r.p10_recomputed,
    s.median_amount,
    r.median_recomputed,
    s.p90_amount,
    r.p90_recomputed
from {{ ref('gld_mart__service_price_summary') }} as s
join recomputed as r
    on s.service_context_key = r.service_context_key
where s.meets_hospital_threshold
    and (
        s.hospital_count <> r.hospital_count
        or cast(s.p10_amount as double)
            is distinct from cast(r.p10_recomputed as double)
        or cast(s.median_amount as double)
            is distinct from cast(r.median_recomputed as double)
        or cast(s.p90_amount as double)
            is distinct from cast(r.p90_recomputed as double)
    )
