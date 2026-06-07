select m.*
from {{ ref('slv_base__modifiers') }} m
inner join {{ ref('val__modifier_rejections') }} r
    on m.snapshot_id = r.snapshot_id
    and m.source_modifier_code_id = r.modifier_code_id
