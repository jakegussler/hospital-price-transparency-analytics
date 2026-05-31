select ci.*
from {{ ref('slv_base__charge_items') }} ci
inner join {{ ref('val__charge_item_rejections') }} r
    on ci.snapshot_id = r.snapshot_id
    and (
        (r.source_format_family = 'json' and ci.source_charge_item_id = r.source_charge_item_id)
        or (r.source_format_family = 'csv' and r.row_ordinal between ci.first_source_row_ordinal and ci.last_source_row_ordinal)
    )
