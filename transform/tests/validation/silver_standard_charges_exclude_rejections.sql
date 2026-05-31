select sc.*
from {{ ref('slv_base__standard_charges') }} sc
inner join {{ ref('val__standard_charge_rejections') }} r
    on sc.snapshot_id = r.snapshot_id
    and (
        (r.source_format_family = 'json' and sc.source_standard_charge_id = r.source_standard_charge_id)
        or (r.source_format_family = 'csv' and r.row_ordinal between sc.first_source_row_ordinal and sc.last_source_row_ordinal)
    )
