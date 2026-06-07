select distinct
    snapshot_id,
    hospital_id,
    source_format,
    source_format_family,
    npi_ordinal,
    rule_id,
    diagnostic_type,
    message
from {{ ref('val__all_violations') }}
where excludes_from_silver
    and grain = 'npi'
