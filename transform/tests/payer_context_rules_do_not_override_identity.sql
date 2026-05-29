select
    core.silver_payer_rate_id,
    core.clean_payer_name,
    core.clean_plan_name,
    core.canonical_payer_id as core_canonical_payer_id,
    alias_matches.canonical_payer_id as alias_canonical_payer_id,
    core.payer_context_rule_id
from {{ ref('slv_core__payer_rates') }} core
inner join {{ ref('slv_core__payer_alias_matches') }} alias_matches
    on core.silver_payer_rate_id = alias_matches.silver_payer_rate_id
where core.canonical_payer_id is distinct from alias_matches.canonical_payer_id
