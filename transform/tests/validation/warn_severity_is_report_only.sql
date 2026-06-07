-- Guard: severity (seriousness) and disposition (routing) are orthogonal, but
-- one combination is illegal. A warn-severity rule is a soft/recommended-value
-- advisory and must never change record routing, so it must be report_only.
-- (An error-severity rule may legitimately exclude, be report-only, or be
-- already-quarantined depending on grain, so it is not constrained here.)
-- Test passes when this query returns zero rows.
select
    rule_id,
    severity,
    disposition
from {{ ref('cms_validation_rules') }}
where severity = 'warn'
    and disposition != 'report_only'
