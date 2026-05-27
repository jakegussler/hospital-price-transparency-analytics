select aliases.*
from {{ ref('payer_aliases') }} aliases
left join {{ ref('canonical_payers') }} canonical_payers
    on aliases.canonical_payer_id = canonical_payers.canonical_payer_id
where aliases.active = true
    and aliases.review_status = 'accepted'
    and coalesce(canonical_payers.active, false) <> true
