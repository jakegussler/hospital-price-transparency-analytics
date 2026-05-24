select
    r.snapshot_id,
    r.row_ordinal
from {{ ref('stg_bronze__csv_charge_rows') }} r
left join {{ ref('slv_base__payer_rates') }} pr
    on r.snapshot_id = pr.snapshot_id
    and r.row_ordinal = pr.source_row_ordinal
    and r.source_rate_ordinal = pr.source_rate_ordinal
where pr.silver_payer_rate_id is null
