select distinct
    snapshot_id,
    hospital_id,
    source_format,
    source_format_family,
    source_charge_item_id,
    source_standard_charge_id,
    row_ordinal,
    rule_id,
    severity,
    diagnostic_type,
    message
from {{ hpt_scoped_ref('val__all_violations') }}
where excludes_from_silver
    and grain = 'standard_charge'
