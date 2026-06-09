select
    {{ hpt_surrogate_key([
        'pr.silver_payer_rate_id',
        'm.silver_charge_modifier_member_id'
    ]) }} as silver_payer_rate_modifier_id,
    pr.silver_payer_rate_id,
    m.silver_charge_modifier_member_id,
    m.silver_charge_modifier_declaration_id,
    pr.silver_standard_charge_id,
    pr.silver_charge_item_id,
    pr.snapshot_id,
    pr.hospital_id,
    pr.source_format,
    pr.source_row_ordinal,
    pr.source_rate_ordinal,
    m.member_ordinal,
    m.raw_modifier_code,
    m.clean_modifier_code,
    m.resolved_silver_modifier_id,
    m.modifier_definition_match_status
from {{ ref('slv_base__payer_rates') }} pr
inner join {{ ref('slv_base__charge_modifier_members') }} m
    on pr.snapshot_id = m.snapshot_id
    and pr.source_row_ordinal = m.source_row_ordinal
where pr.source_format like 'csv%'
