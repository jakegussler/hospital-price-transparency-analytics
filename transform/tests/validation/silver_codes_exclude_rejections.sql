select c.*
from {{ ref('slv_base__charge_item_codes') }} c
inner join {{ ref('val__code_rejections') }} r
    on c.snapshot_id = r.snapshot_id
    and c.code_ordinal = r.code_ordinal
    and r.source_format_family = 'json'
    and c.silver_charge_item_id in (
        select silver_charge_item_id
        from {{ ref('slv_base__charge_items') }}
        where source_charge_item_id = r.source_charge_item_id
    )
