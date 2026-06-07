select row_items.*
from {{ ref('slv_base__csv_charge_row_items') }} row_items
inner join {{ ref('val__charge_item_rejections') }} r
    on r.source_format_family = 'csv'
    and row_items.snapshot_id = r.snapshot_id
    and row_items.row_ordinal = r.row_ordinal
