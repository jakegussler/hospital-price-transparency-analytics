-- Modifier codes attached to a Silver standard charge, at one uniform grain for
-- both formats: one row per (silver_standard_charge_id, modifier_ordinal,
-- clean_modifier_code). Modifiers belong to the standard charge and apply to
-- every payer rate beneath it; the standard-charge -> payer-rate fan-out is done
-- once downstream in slv_core__rate_modifier_signature, never duplicated here.
--
-- For CSV, raw_modifiers is part of the standard_charge_signature, so it is
-- constant across the payer-rate rows that collapse into one standard charge.
-- We therefore unnest it directly from slv_base__standard_charges (the grain
-- parent) rather than re-deriving it per row and joining payer rates, which both
-- avoids the redundant per-rate duplication and keeps modifiers on standard
-- charges whose only source rows carry no payer (item-only CSV rows).
with modifier_definitions as (
    select
        snapshot_id,
        clean_modifier_code,
        min(source_modifier_code_id) as source_modifier_code_id
    from {{ hpt_scoped_ref('slv_base__modifiers') }}
    group by snapshot_id, clean_modifier_code
),

json_modifiers as (
    select
        standard_charges.silver_standard_charge_id,
        standard_charges.silver_charge_item_id,
        scm.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        standard_charges.source_standard_charge_id,
        scm.modifier_ordinal,
        scm.raw_modifier_code,
        scm.clean_modifier_code,
        m.source_modifier_code_id,
        case
            when m.source_modifier_code_id is null then 'unresolved'
            else 'resolved'
        end as modifier_definition_match_status
    from {{ hpt_scoped_ref('stg_bronze__standard_charge_modifiers') }} scm
    inner join {{ hpt_scoped_ref('slv_base__standard_charges') }} standard_charges
        on scm.snapshot_id = standard_charges.snapshot_id
        and scm.standard_charge_id = standard_charges.source_standard_charge_id
    left join modifier_definitions m
        on scm.snapshot_id = m.snapshot_id
        and scm.clean_modifier_code = m.clean_modifier_code
),

csv_modifiers as (
    select
        standard_charges.silver_standard_charge_id,
        standard_charges.silver_charge_item_id,
        standard_charges.snapshot_id,
        standard_charges.hospital_id,
        standard_charges.source_format,
        cast(null as varchar) as source_standard_charge_id,
        cast(u.modifier_ordinal as integer) - 1 as modifier_ordinal,
        u.raw_modifier_code,
        {{ hpt_clean_display_text('u.raw_modifier_code') }} as clean_modifier_code,
        cast(null as varchar) as source_modifier_code_id,
        'not_available_for_csv' as modifier_definition_match_status
    from {{ hpt_scoped_ref('slv_base__standard_charges') }} standard_charges
    cross join unnest(string_split(standard_charges.raw_modifiers, '|'))
        with ordinality as u(raw_modifier_code, modifier_ordinal)
    where standard_charges.raw_modifiers is not null
        and {{ hpt_clean_display_text('u.raw_modifier_code') }} is not null
)

select
    {{ hpt_surrogate_key([
        'silver_standard_charge_id',
        'modifier_ordinal',
        'clean_modifier_code'
    ]) }} as silver_charge_modifier_id,
    *
from json_modifiers

union all

select
    {{ hpt_surrogate_key([
        'silver_standard_charge_id',
        'modifier_ordinal',
        'clean_modifier_code'
    ]) }} as silver_charge_modifier_id,
    *
from csv_modifiers
