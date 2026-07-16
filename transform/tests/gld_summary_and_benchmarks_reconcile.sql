-- Cross-model reconciliation (decision 0021): the service summary and the
-- hospital benchmarks must describe the SAME hospital-weighted distribution.
-- Before 0021 the project published two different P10 definitions for one
-- context (observation-weighted in the summary, hospital-weighted in the
-- benchmarks); both now read gld_int__hospital_service_amounts, and this guard
-- keeps them from drifting apart again.
with benchmark_stats as (
    select
        service_context_key,
        any_value(peer_hospital_count_all) as peer_hospital_count_all,
        any_value(market_median_all) as market_median_all,
        any_value(market_p10_all) as market_p10_all,
        any_value(market_p90_all) as market_p90_all
    from {{ ref('gld_mart__hospital_service_benchmarks') }}
    group by 1
)

select
    s.service_context_key
from {{ ref('gld_mart__service_price_summary') }} as s
join benchmark_stats as b
    on s.service_context_key = b.service_context_key
where s.meets_hospital_threshold
    and (
        s.hospital_count <> b.peer_hospital_count_all
        or cast(s.median_amount as double)
            is distinct from cast(b.market_median_all as double)
        or cast(s.p10_amount as double)
            is distinct from cast(b.market_p10_all as double)
        or cast(s.p90_amount as double)
            is distinct from cast(b.market_p90_all as double)
    )
