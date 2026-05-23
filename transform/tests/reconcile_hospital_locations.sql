select
    l.snapshot_id,
    l.location_ordinal
from {{ ref('stg_bronze__hospital_locations') }} l
left join {{ ref('slv_base__hospital_snapshots') }} s
    on l.snapshot_id = s.snapshot_id
where s.snapshot_id is null
