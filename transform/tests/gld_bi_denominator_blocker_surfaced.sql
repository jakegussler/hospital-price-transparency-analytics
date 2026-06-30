-- Contract guard: the cohort-grain below_min_hospital_denominator blocker
-- (decision 0017) must stay visible in the BI layer as
-- gld_bi__service_market_explorer.comparison_status = 'insufficient_denominator'.
--
-- gld_bi__comparison_blocker_summary intentionally omits this 11th blocker (it
-- covers only the 10 atomic row-grain blockers). The denominator floor is a
-- service-context cohort/window property, so 'insufficient_denominator' is the
-- canonical thin-cohort signal. If a refactor ever decouples the status from the
-- floor, the UI would silently hide thin cohorts. Lock the biconditional:
-- comparison_status = 'insufficient_denominator' IFF the cohort is below floor
-- (not meets_hospital_threshold). Non-vacuous: the corpus has both thin and
-- adequate cohorts.
select *
from {{ ref('gld_bi__service_market_explorer') }}
where (not meets_hospital_threshold)
    <> (comparison_status = 'insufficient_denominator')
