select
    source_format,
    modifier_definition_match_status,
    count(*) as declaration_rows,
    count(distinct silver_standard_charge_id) as standard_charge_rows_with_modifiers,
    count(distinct snapshot_id) as snapshots
from {{ ref('slv_base__charge_modifier_declarations') }}
group by source_format, modifier_definition_match_status
order by source_format, modifier_definition_match_status
