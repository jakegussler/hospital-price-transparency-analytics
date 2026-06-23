select
    clean_payer_name,
    match_scope,
    canonical_state,
    count(*) as alias_count
from {{ ref('payer_aliases') }}
where active = true
group by clean_payer_name, match_scope, canonical_state
having count(*) > 1
