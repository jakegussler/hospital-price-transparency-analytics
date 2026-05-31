select s.*
from {{ ref('slv_base__hospital_snapshots') }} s
inner join {{ ref('val__snapshot_rejections') }} r
    on s.snapshot_id = r.snapshot_id
