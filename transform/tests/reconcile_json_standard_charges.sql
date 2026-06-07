select
    sc.snapshot_id,
    sc.standard_charge_id
from {{ ref('stg_bronze__standard_charges') }} sc
left join {{ ref('slv_base__standard_charges') }} standard_charges
    on sc.snapshot_id = standard_charges.snapshot_id
    and sc.standard_charge_id = standard_charges.source_standard_charge_id
where standard_charges.silver_standard_charge_id is null
    and not exists (
        select 1
        from {{ ref('val__charge_item_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = sc.snapshot_id
            and r.source_charge_item_id = sc.charge_item_id
    )
    and not exists (
        select 1
        from {{ ref('val__standard_charge_rejections') }} r
        where r.source_format_family = 'json'
            and r.snapshot_id = sc.snapshot_id
            and r.source_standard_charge_id = sc.standard_charge_id
    )
