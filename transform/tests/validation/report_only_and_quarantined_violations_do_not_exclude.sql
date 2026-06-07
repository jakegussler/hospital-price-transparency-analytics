select *
from {{ ref('val__all_violations') }}
where disposition in ('report_only', 'already_quarantined')
    and excludes_from_silver
