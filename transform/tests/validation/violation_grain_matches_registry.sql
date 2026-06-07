select
    v.validation_violation_id,
    v.rule_id,
    v.grain as emitted_grain,
    r.grain as registry_grain
from {{ ref('val__all_violations') }} v
inner join {{ ref('cms_validation_rules') }} r using (rule_id)
where v.grain <> r.grain
