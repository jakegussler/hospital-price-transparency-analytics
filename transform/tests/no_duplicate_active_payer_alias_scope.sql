select
    clean_payer_name,
    match_scope,
    canonical_state,
    count(*) as active_alias_count
from {{ ref('payer_aliases') }}
where active = true
    and review_status = 'accepted'
group by clean_payer_name, match_scope, canonical_state
having count(*) > 1
