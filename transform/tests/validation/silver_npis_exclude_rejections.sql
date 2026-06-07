select n.*
from {{ ref('slv_base__type2_npis') }} n
inner join {{ ref('val__npi_rejections') }} r
    on n.snapshot_id = r.snapshot_id
    and n.npi_ordinal = r.npi_ordinal
