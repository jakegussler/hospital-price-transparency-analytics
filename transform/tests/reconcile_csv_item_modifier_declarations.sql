with signed_source_rows as (
    select distinct
        r.snapshot_id,
        r.row_ordinal,
        ri.silver_charge_item_id,
        {{ hpt_surrogate_key([
            'r.snapshot_id',
            'ri.silver_charge_item_id',
            'r.raw_setting',
            'r.clean_setting',
            'r.raw_billing_class',
            'r.clean_billing_class',
            'r.gross_charge',
            'r.discounted_cash',
            'r.minimum',
            'r.maximum',
            'r.raw_modifiers',
            'r.additional_generic_notes'
        ]) }} as standard_charge_signature
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on r.snapshot_id = mr.snapshot_id
        and r.row_ordinal = mr.row_ordinal
        and mr.is_item_associated_modifier
    inner join {{ ref('slv_base__csv_charge_row_items') }} ri
        on r.snapshot_id = ri.snapshot_id
        and r.row_ordinal = ri.row_ordinal
    where 1 = 1
        {{ hpt_snapshot_filter('r') }}
),

expected as (
    select r.snapshot_id, r.row_ordinal
    from signed_source_rows r
    inner join {{ ref('slv_base__standard_charges') }} sc
        on r.snapshot_id = sc.snapshot_id
        and r.silver_charge_item_id = sc.silver_charge_item_id
        and r.standard_charge_signature = sc.standard_charge_signature
),

actual as (
    select snapshot_id, source_row_ordinal as row_ordinal
    from {{ ref('slv_base__charge_modifier_declarations') }}
    where declaration_kind = 'csv_item_declaration'
        {{ hpt_snapshot_filter() }}
)

select 'missing' as mismatch_type, * from expected
except
select 'missing' as mismatch_type, * from actual

union all

select 'unexpected' as mismatch_type, * from actual
except
select 'unexpected' as mismatch_type, * from expected
