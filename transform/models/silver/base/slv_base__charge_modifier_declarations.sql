with json_declarations as (
    select
        {{ hpt_surrogate_key([
            'scm.snapshot_id', "'json'", 'scm.standard_charge_id', 'scm.modifier_ordinal'
        ]) }} as silver_charge_modifier_declaration_id,
        'json_charge_declaration' as declaration_kind,
        sc.silver_standard_charge_id,
        sc.silver_charge_item_id,
        scm.snapshot_id,
        sc.hospital_id,
        sc.source_format,
        sc.source_standard_charge_id,
        cast(null as integer) as source_row_ordinal,
        scm.modifier_ordinal as source_modifier_ordinal,
        scm.raw_modifier_code as raw_modifier_combination,
        scm.clean_modifier_code as clean_modifier_combination,
        sc.raw_setting,
        sc.clean_setting
    from {{ ref('stg_bronze__standard_charge_modifiers') }} scm
    inner join {{ ref('slv_base__standard_charges') }} sc
        on scm.snapshot_id = sc.snapshot_id
        and scm.standard_charge_id = sc.source_standard_charge_id
    where scm.clean_modifier_code is not null
),

csv_source_rows as (
    select distinct
        r.snapshot_id,
        r.row_ordinal,
        ri.silver_charge_item_id,
        r.raw_setting,
        r.clean_setting,
        r.raw_billing_class,
        r.clean_billing_class,
        r.gross_charge,
        r.discounted_cash,
        r.minimum,
        r.maximum,
        r.raw_modifiers,
        r.additional_generic_notes,
        mr.raw_modifier_combination,
        mr.clean_modifier_combination
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on r.snapshot_id = mr.snapshot_id
        and r.row_ordinal = mr.row_ordinal
        and mr.is_item_associated_modifier
    inner join {{ ref('slv_base__csv_charge_row_items') }} ri
        on r.snapshot_id = ri.snapshot_id
        and r.row_ordinal = ri.row_ordinal
),

csv_signed_rows as (
    select
        *,
        {{ hpt_surrogate_key([
            'snapshot_id',
            'silver_charge_item_id',
            'raw_setting',
            'clean_setting',
            'raw_billing_class',
            'clean_billing_class',
            'gross_charge',
            'discounted_cash',
            'minimum',
            'maximum',
            'raw_modifiers',
            'additional_generic_notes'
        ]) }} as standard_charge_signature
    from csv_source_rows
),

csv_declarations as (
    select
        {{ hpt_surrogate_key(['r.snapshot_id', "'csv'", 'r.row_ordinal']) }} as silver_charge_modifier_declaration_id,
        'csv_item_declaration' as declaration_kind,
        sc.silver_standard_charge_id,
        sc.silver_charge_item_id,
        r.snapshot_id,
        sc.hospital_id,
        sc.source_format,
        cast(null as varchar) as source_standard_charge_id,
        r.row_ordinal as source_row_ordinal,
        cast(null as integer) as source_modifier_ordinal,
        r.raw_modifier_combination,
        r.clean_modifier_combination,
        r.raw_setting,
        r.clean_setting
    from csv_signed_rows r
    inner join {{ ref('slv_base__standard_charges') }} sc
        on r.snapshot_id = sc.snapshot_id
        and r.silver_charge_item_id = sc.silver_charge_item_id
        and r.standard_charge_signature = sc.standard_charge_signature
),

declarations as (
    select * from json_declarations
    union all
    select * from csv_declarations
),

definition_candidates as (
    select
        d.silver_charge_modifier_declaration_id,
        count(m.silver_modifier_id) as candidate_count,
        max(m.silver_modifier_id) as candidate_silver_modifier_id
    from declarations d
    left join {{ ref('slv_base__modifiers') }} m
        on d.snapshot_id = m.snapshot_id
        and d.clean_modifier_combination = m.clean_modifier_combination
        and (
            d.clean_setting is null
            or m.clean_setting is null
            or d.clean_setting = m.clean_setting
        )
    group by d.silver_charge_modifier_declaration_id
)

select
    d.*,
    case when c.candidate_count = 1 then c.candidate_silver_modifier_id end as resolved_silver_modifier_id,
    case
        when c.candidate_count = 1 then 'resolved_exact'
        when c.candidate_count > 1 then 'ambiguous'
        else 'unresolved'
    end as modifier_definition_match_status
from declarations d
inner join definition_candidates c
    on d.silver_charge_modifier_declaration_id = c.silver_charge_modifier_declaration_id
