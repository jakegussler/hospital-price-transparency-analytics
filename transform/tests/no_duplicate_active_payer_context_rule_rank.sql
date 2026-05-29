select
    source_canonical_payer_id,
    source_clean_payer_name,
    plan_pattern,
    match_type,
    match_scope,
    match_state,
    priority,
    count(*) as active_rule_count
from {{ ref('payer_context_rules') }}
where active = true
    and review_status = 'accepted'
group by
    source_canonical_payer_id,
    source_clean_payer_name,
    plan_pattern,
    match_type,
    match_scope,
    match_state,
    priority
having count(*) > 1
