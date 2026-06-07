select
    r.rule_id,
    r.rule_name,
    r.grain,
    r.severity,
    r.applies_to_formats,
    count(v.validation_violation_id) as violation_count,
    count(distinct v.snapshot_id) as affected_snapshot_count,
    count(distinct v.hospital_id) as affected_hospital_count,
    count(*) filter (where v.excludes_from_silver) as rejected_violation_count,
    string_agg(distinct v.diagnostic_type, ', ' order by v.diagnostic_type) as diagnostic_types
from {{ ref('cms_validation_rules') }} r
left join {{ ref('val__all_violations') }} v
    on r.rule_id = v.rule_id
    and v.snapshot_id in (
        {{ hpt_current_snapshot_ids_sql() }}
    )
group by
    r.rule_id,
    r.rule_name,
    r.grain,
    r.severity,
    r.applies_to_formats
