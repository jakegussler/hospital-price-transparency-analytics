select
    rule_id,
    rule_name,
    grain,
    severity,
    applies_to_formats,
    target_dbt_model as primary_model,
    'implemented' as implementation_status,
    case
        when disposition = 'already_quarantined'
            then 'Structural parser diagnostics report records already removed before Bronze row construction.'
        when disposition = 'report_only'
            then 'The rule remains queryable but does not exclude Silver entities.'
        else 'The rule creates an exact-grain rejection key when source keys are available.'
    end as coverage_notes
from {{ ref('cms_validation_rules') }}
