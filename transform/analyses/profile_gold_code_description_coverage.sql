-- Profiling: enrichment legibility coverage by code system.
-- Of the cross-hospital-comparable code cohorts in gld_dim__service_code, how
-- many now carry a human-readable description from green-light reference data
-- (MS-DRG today)? Licensed systems (cpt/cdt) and not-yet-loaded systems stay
-- null until enrichment extends (decision 0019).
select
    canonical_code_system,
    count(*) as comparable_code_cohorts,
    sum(has_code_description::int) as cohorts_with_description,
    round(sum(has_code_description::int) / count(*)::double, 4) as description_coverage,
    any_value(code_description_edition) filter (where has_code_description) as edition,
    any_value(code_description_license) filter (where has_code_description) as license
from {{ ref('gld_dim__service_code') }}
group by 1
order by comparable_code_cohorts desc
