select overrides.*
from {{ ref('payer_context_overrides') }} overrides
left join {{ ref('canonical_payers') }} canonical_payers
    on overrides.canonical_payer_id = canonical_payers.canonical_payer_id
where overrides.active = true
    and overrides.review_status = 'accepted'
    and coalesce(canonical_payers.active, false) <> true
