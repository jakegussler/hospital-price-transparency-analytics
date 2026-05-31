select rules.*
from {{ ref('payer_context_rules') }} rules
left join {{ ref('states') }} states
    on rules.match_state = states.state_code
where active = true
    and review_status = 'accepted'
    and match_scope = 'state'
    and states.state_code is null
