select *
from {{ ref('slv_base__charge_modifier_declarations') }}
where modifier_definition_match_status <> 'resolved_exact'
    and resolved_silver_modifier_id is not null
