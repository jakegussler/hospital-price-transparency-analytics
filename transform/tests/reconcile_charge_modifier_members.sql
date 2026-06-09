select
    d.silver_charge_modifier_declaration_id,
    d.clean_modifier_combination,
    string_agg(m.clean_modifier_code, '|' order by m.member_ordinal) as reconstructed_combination
from {{ ref('slv_base__charge_modifier_declarations') }} d
left join {{ ref('slv_base__charge_modifier_members') }} m
    on d.silver_charge_modifier_declaration_id = m.silver_charge_modifier_declaration_id
group by d.silver_charge_modifier_declaration_id, d.clean_modifier_combination
having reconstructed_combination is distinct from d.clean_modifier_combination
