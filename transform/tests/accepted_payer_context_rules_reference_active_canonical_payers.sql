select rules.*
from {{ ref('payer_context_rules') }} rules
left join {{ ref('canonical_payers') }} canonical_payers
    on rules.source_canonical_payer_id = canonical_payers.canonical_payer_id
where rules.active = true
    and rules.review_status = 'accepted'
    and coalesce(canonical_payers.active, false) <> true
