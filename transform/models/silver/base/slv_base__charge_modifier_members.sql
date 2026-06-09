select
    {{ hpt_surrogate_key([
        'd.silver_charge_modifier_declaration_id',
        'u.member_ordinal',
        'u.raw_modifier_code'
    ]) }} as silver_charge_modifier_member_id,
    d.silver_charge_modifier_declaration_id,
    d.silver_standard_charge_id,
    d.silver_charge_item_id,
    d.resolved_silver_modifier_id,
    d.snapshot_id,
    d.hospital_id,
    d.source_format,
    d.source_standard_charge_id,
    d.source_row_ordinal,
    cast(u.member_ordinal as integer) - 1 as member_ordinal,
    u.raw_modifier_code,
    {{ hpt_clean_display_text('u.raw_modifier_code') }} as clean_modifier_code,
    d.modifier_definition_match_status
from {{ ref('slv_base__charge_modifier_declarations') }} d
cross join unnest(string_split(d.raw_modifier_combination, '|'))
    with ordinality as u(raw_modifier_code, member_ordinal)
where {{ hpt_clean_display_text('u.raw_modifier_code') }} is not null
