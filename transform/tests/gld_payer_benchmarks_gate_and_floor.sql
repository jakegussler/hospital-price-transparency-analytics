-- Semantic guards (plan §10.4 / §7.4): gld_mart__payer_service_benchmarks must (a) never
-- contain an unmatched/null payer (payer identity is the prerequisite gate) and
-- (b) never publish the payer-market median below its 3-hospital floor.
select *
from {{ ref('gld_mart__payer_service_benchmarks') }}
where canonical_payer_id is null
    or canonical_payer_id = '<unmatched>'
    or (
        payer_market_median_negotiated is not null
        and coalesce(payer_hospital_count, 0) < 3
    )
