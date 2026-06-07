select p.*
from {{ ref('slv_base__general_contract_provisions') }} p
inner join {{ ref('val__provision_rejections') }} r
    on p.snapshot_id = r.snapshot_id
    and p.provision_ordinal = r.provision_ordinal
