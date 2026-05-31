select distinct
    snapshot_id,
    hospital_id,
    source_format,
    source_format_family,
    rule_id,
    severity,
    diagnostic_type,
    message
from {{ ref('val__all_violations') }}
where severity = 'reject'
    and grain in ('file', 'header')
