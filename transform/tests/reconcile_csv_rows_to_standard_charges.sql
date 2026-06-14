-- Every CSV Bronze row's item must surface as a Silver standard charge or be
-- rejected. This reconciles through the row's charge item (not through a payer
-- rate), so item-only rows -- CSV Tall item-only rows and CSV Wide item-only
-- baseline rows that carry no payer rate -- are still accounted for.
select
    r.snapshot_id,
    r.row_ordinal
from {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
left join {{ hpt_scoped_ref('slv_base__csv_charge_row_items') }} row_items
    on r.snapshot_id = row_items.snapshot_id
    and r.row_ordinal = row_items.row_ordinal
left join {{ hpt_scoped_ref('slv_base__standard_charges') }} standard_charges
    on row_items.silver_charge_item_id = standard_charges.silver_charge_item_id
where standard_charges.silver_standard_charge_id is null
    and not exists (
        select 1
        from {{ hpt_scoped_ref('val__charge_item_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
    )
    and not exists (
        select 1
        from {{ hpt_scoped_ref('val__standard_charge_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
    )
