select *
from {{ ref('payer_context_rules') }}
where active = true
    and review_status = 'accepted'
    and match_scope = 'state'
    and {{ hpt_clean_text('match_state') }} is null
