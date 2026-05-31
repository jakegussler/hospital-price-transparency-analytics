select distinct
    snapshot_id,
    hospital_id,
    source_format,
    source_format_family,
    source_standard_charge_id,
    payer_ordinal,
    row_ordinal,
    source_rate_ordinal,
    rule_id,
    severity,
    diagnostic_type,
    message
from {{ ref('val__all_violations') }}
where severity = 'reject'
    and grain = 'payer_rate'
