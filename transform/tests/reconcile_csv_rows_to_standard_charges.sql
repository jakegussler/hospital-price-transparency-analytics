select
    r.snapshot_id,
    r.row_ordinal
from {{ ref('stg_bronze__csv_charge_rows') }} r
left join {{ ref('slv_base__standard_charges') }} standard_charges
    on r.snapshot_id = standard_charges.snapshot_id
    and r.row_ordinal = standard_charges.source_row_ordinal
where standard_charges.silver_standard_charge_id is null
