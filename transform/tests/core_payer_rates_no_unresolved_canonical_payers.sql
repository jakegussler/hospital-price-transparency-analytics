select core.*
from {{ ref('slv_core__payer_rates') }} core
left join {{ ref('canonical_payers') }} canonical_payers
    on core.canonical_payer_id = canonical_payers.canonical_payer_id
where core.canonical_payer_id is not null
    and canonical_payers.canonical_payer_id is null
