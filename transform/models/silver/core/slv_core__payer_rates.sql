select
    pr.*,
    alias_matches.canonical_payer_id,
    canonical_payers.canonical_payer_name,
    canonical_payers.payer_parent_id,
    canonical_payers.payer_parent_name,
    canonical_payers.payer_type,
    coalesce(
        context_matches.market_segment,
        {{ hpt_clean_text('canonical_payers.default_market_segment') }},
        'unknown'
    ) as market_segment,
    context_matches.program_type,
    context_matches.product_or_network_name,
    context_matches.subsidiary_or_brand,
    coalesce(
        context_matches.benefit_line,
        {{ hpt_clean_text('canonical_payers.default_benefit_line') }},
        'unknown'
    ) as benefit_line,
    context_matches.funding_arrangement,
    context_matches.context_state,
    context_matches.plan_type,
    case
        when alias_matches.canonical_payer_id is not null then 'payer_alias'
        else 'unmatched'
    end as payer_match_basis,
    case
        when context_matches.payer_context_rule_id is not null then 'payer_context_rule'
        else 'no_context_rule'
    end as payer_context_match_basis,
    alias_matches.payer_alias_id,
    context_matches.payer_context_rule_id,
    coalesce(alias_matches.payer_review_status, 'candidate') as payer_review_status,
    context_matches.payer_context_review_status,
    context_matches.payer_context_confidence
from {{ hpt_scoped_ref('slv_base__payer_rates') }} pr
left join {{ ref('slv_core__payer_alias_matches') }} alias_matches
    on pr.silver_payer_rate_id = alias_matches.silver_payer_rate_id
left join {{ ref('slv_core__payer_context_matches') }} context_matches
    on pr.silver_payer_rate_id = context_matches.silver_payer_rate_id
left join {{ ref('canonical_payers') }} canonical_payers
    on alias_matches.canonical_payer_id = canonical_payers.canonical_payer_id
    and canonical_payers.active = true
