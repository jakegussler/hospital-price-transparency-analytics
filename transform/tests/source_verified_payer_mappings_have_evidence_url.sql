select
    'canonical_payers' as seed_name,
    canonical_payer_id as record_id,
    evidence_source,
    evidence_url
from {{ ref('canonical_payers') }}
where evidence_source <> 'manual_review'
    and {{ hpt_clean_text('evidence_url') }} is null

union all

select
    'payer_aliases' as seed_name,
    payer_alias_id as record_id,
    evidence_source,
    evidence_url
from {{ ref('payer_aliases') }}
where evidence_source <> 'manual_review'
    and {{ hpt_clean_text('evidence_url') }} is null

union all

select
    'payer_context_rules' as seed_name,
    payer_context_rule_id as record_id,
    evidence_source,
    evidence_url
from {{ ref('payer_context_rules') }}
where evidence_source <> 'manual_review'
    and {{ hpt_clean_text('evidence_url') }} is null
