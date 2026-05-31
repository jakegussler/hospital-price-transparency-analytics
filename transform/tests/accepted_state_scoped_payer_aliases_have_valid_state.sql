select aliases.*
from {{ ref('payer_aliases') }} aliases
left join {{ ref('states') }} states
    on aliases.canonical_state = states.state_code
where aliases.active = true
    and aliases.review_status = 'accepted'
    and aliases.match_scope = 'state'
    and states.state_code is null
