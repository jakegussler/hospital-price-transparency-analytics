select d.*
from {{ ref('slv_base__drug_information') }} d
inner join {{ ref('val__drug_rejections') }} r
    on d.snapshot_id = r.snapshot_id
    and (
        (r.source_format_family = 'json' and d.source_charge_item_id = r.source_charge_item_id)
        or (r.source_format_family = 'csv' and d.source_row_ordinal = r.row_ordinal)
    )
