select
    sc.snapshot_id,
    sc.standard_charge_id
from {{ ref('stg_bronze__standard_charges') }} sc
left join {{ ref('slv_base__standard_charges') }} standard_charges
    on sc.snapshot_id = standard_charges.snapshot_id
    and sc.standard_charge_id = standard_charges.source_standard_charge_id
where standard_charges.silver_standard_charge_id is null
