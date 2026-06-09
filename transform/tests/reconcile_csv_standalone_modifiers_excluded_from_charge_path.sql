select mr.*
from {{ ref('stg_bronze__csv_modifier_rows') }} mr
inner join {{ ref('slv_base__csv_charge_row_items') }} ri
    on mr.snapshot_id = ri.snapshot_id
    and mr.row_ordinal = ri.row_ordinal
where mr.is_standalone_modifier
    {{ hpt_snapshot_filter('mr') }}
