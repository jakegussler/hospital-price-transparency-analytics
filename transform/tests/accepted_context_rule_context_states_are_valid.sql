select rules.*
from {{ ref('payer_context_rules') }} rules
left join {{ ref('states') }} states
    on rules.context_state = states.state_code
where rules.active = true
    and rules.review_status = 'accepted'
    and {{ hpt_clean_text('rules.context_state') }} is not null
    and states.state_code is null
