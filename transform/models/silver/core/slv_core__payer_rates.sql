select
    pr.*,
    coalesce(context_matches.canonical_payer_id, alias_matches.canonical_payer_id) as canonical_payer_id,
    canonical_payers.canonical_payer_name,
    canonical_payers.parent_organization,
    canonical_payers.payer_category,
    case
        when context_matches.canonical_payer_id is not null then 'payer_context_override'
        when alias_matches.canonical_payer_id is not null then 'payer_alias'
        else 'unmatched'
    end as payer_match_basis,
    alias_matches.payer_alias_id,
    context_matches.payer_context_rule_id,
    coalesce(context_matches.payer_review_status, alias_matches.payer_review_status, 'candidate') as payer_review_status
from {{ ref('slv_base__payer_rates') }} pr
left join {{ ref('slv_core__payer_alias_matches') }} alias_matches
    on pr.silver_payer_rate_id = alias_matches.silver_payer_rate_id
left join {{ ref('slv_core__payer_context_matches') }} context_matches
    on pr.silver_payer_rate_id = context_matches.silver_payer_rate_id
left join {{ ref('canonical_payers') }} canonical_payers
    on coalesce(context_matches.canonical_payer_id, alias_matches.canonical_payer_id) = canonical_payers.canonical_payer_id
    and canonical_payers.active = true
