select
    l.snapshot_id,
    l.location_ordinal
from {{ ref('stg_bronze__hospital_locations') }} l
left join {{ ref('slv_base__hospital_snapshots') }} s
    on l.snapshot_id = s.snapshot_id
where s.snapshot_id is null
    and not exists (
        select 1
        from {{ ref('val__snapshot_rejections') }} r
        where r.snapshot_id = l.snapshot_id
    )
