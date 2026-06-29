-- Semantic guard (plan §10.4): gld_mart__hospital_service_benchmarks must not publish a
-- peer-group market statistic below that peer group's 3-hospital floor. For each of
-- the four peer groups, a non-null median implies its hospital count >= 3.
select *
from {{ ref('gld_mart__hospital_service_benchmarks') }}
where (market_median_all is not null and coalesce(peer_hospital_count_all, 0) < 3)
    or (market_median_state is not null and coalesce(peer_hospital_count_state, 0) < 3)
    or (market_median_type is not null and coalesce(peer_hospital_count_type, 0) < 3)
    or (market_median_system is not null and coalesce(peer_hospital_count_system, 0) < 3)
