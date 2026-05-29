select *
from {{ ref('payer_context_rules') }}
where active = true
    and review_status = 'accepted'
    and {{ hpt_clean_text('notes') }} is null
