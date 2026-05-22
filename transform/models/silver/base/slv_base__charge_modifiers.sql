with modifier_definitions as (
    select
        snapshot_id,
        clean_modifier_code,
        min(source_modifier_code_id) as source_modifier_code_id
    from {{ ref('slv_base__modifiers') }}
    group by snapshot_id, clean_modifier_code
),

json_modifiers as (
    select
        standard_charges.silver_standard_charge_id,
        cast(null as varchar) as silver_payer_rate_id,
        standard_charges.silver_charge_item_id,
        scm.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        standard_charges.source_standard_charge_id,
        cast(null as integer) as source_row_ordinal,
        scm.modifier_ordinal,
        scm.raw_modifier_code,
        scm.clean_modifier_code,
        m.source_modifier_code_id,
        case
            when m.source_modifier_code_id is null then 'unresolved'
            else 'resolved'
        end as modifier_definition_match_status
    from {{ ref('stg_bronze__standard_charge_modifiers') }} scm
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on scm.snapshot_id = standard_charges.snapshot_id
        and scm.standard_charge_id = standard_charges.source_standard_charge_id
    left join modifier_definitions m
        on scm.snapshot_id = m.snapshot_id
        and scm.clean_modifier_code = m.clean_modifier_code
),

csv_modifier_tokens as (
    select
        r.snapshot_id,
        r.row_ordinal,
        cast(u.modifier_ordinal as integer) - 1 as modifier_ordinal,
        u.raw_modifier_code,
        {{ hpt_clean_display_text('u.raw_modifier_code') }} as clean_modifier_code
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    cross join unnest(string_split(r.raw_modifiers, '|')) with ordinality as u(raw_modifier_code, modifier_ordinal)
    where {{ hpt_clean_display_text('u.raw_modifier_code') }} is not null
),

csv_modifiers as (
    select
        standard_charges.silver_standard_charge_id,
        pr.silver_payer_rate_id,
        standard_charges.silver_charge_item_id,
        c.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        cast(null as varchar) as source_standard_charge_id,
        c.row_ordinal as source_row_ordinal,
        c.modifier_ordinal,
        c.raw_modifier_code,
        c.clean_modifier_code,
        cast(null as varchar) as source_modifier_code_id,
        'not_available_for_csv' as modifier_definition_match_status
    from csv_modifier_tokens c
    inner join {{ ref('slv_base__standard_charges') }} standard_charges
        on c.snapshot_id = standard_charges.snapshot_id
        and c.row_ordinal = standard_charges.source_row_ordinal
    inner join {{ ref('slv_base__payer_rates') }} pr
        on c.snapshot_id = pr.snapshot_id
        and c.row_ordinal = pr.source_row_ordinal
)

select
    {{ hpt_surrogate_key([
        'silver_standard_charge_id',
        'silver_payer_rate_id',
        'modifier_ordinal',
        'clean_modifier_code'
    ]) }} as silver_charge_modifier_id,
    *
from json_modifiers

union all

select
    {{ hpt_surrogate_key([
        'silver_standard_charge_id',
        'silver_payer_rate_id',
        'modifier_ordinal',
        'clean_modifier_code'
    ]) }} as silver_charge_modifier_id,
    *
from csv_modifiers
