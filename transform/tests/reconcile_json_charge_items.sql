select
    sci.snapshot_id,
    sci.charge_item_id
from {{ ref('stg_bronze__standard_charge_info') }} sci
left join {{ ref('slv_base__charge_items') }} ci
    on sci.snapshot_id = ci.snapshot_id
    and sci.charge_item_id = ci.source_charge_item_id
where ci.silver_charge_item_id is null
