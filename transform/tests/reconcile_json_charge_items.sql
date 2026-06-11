select
    sci.snapshot_id,
    sci.charge_item_id
from {{ hpt_scoped_ref('stg_bronze__standard_charge_info') }} sci
left join {{ hpt_scoped_ref('slv_base__charge_items') }} ci
    on sci.snapshot_id = ci.snapshot_id
    and sci.charge_item_id = ci.source_charge_item_id
where ci.silver_charge_item_id is null
    and not exists (
        select 1
        from {{ hpt_scoped_ref('val__charge_item_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = sci.snapshot_id
            and r.source_charge_item_id = sci.charge_item_id
    )
