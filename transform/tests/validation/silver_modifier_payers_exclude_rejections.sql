select mpi.*
from {{ ref('slv_base__modifier_payer_info') }} mpi
inner join {{ ref('val__modifier_payer_rejections') }} r
    on mpi.snapshot_id = r.snapshot_id
    and mpi.source_modifier_code_id = r.modifier_code_id
    and mpi.modifier_payer_ordinal = r.modifier_payer_ordinal
