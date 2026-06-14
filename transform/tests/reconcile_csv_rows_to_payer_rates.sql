-- Every CSV Bronze row that actually encodes a payer rate must surface as a
-- Silver payer rate or be rejected. Item-only rows (CSV Tall item-only rows and
-- CSV Wide item-only baseline rows) carry no payer identity, methodology, or
-- negotiated charge; they are standard charges, not payer rates, and are
-- reconciled by reconcile_csv_rows_to_standard_charges instead.
select
    r.snapshot_id,
    r.row_ordinal
from {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
left join {{ hpt_scoped_ref('slv_base__payer_rates') }} pr
    on r.snapshot_id = pr.snapshot_id
    and r.row_ordinal = pr.source_row_ordinal
    and r.source_rate_ordinal = pr.source_rate_ordinal
where pr.silver_payer_rate_id is null
    and (
        r.clean_payer_name is not null
        or r.clean_plan_name is not null
        or r.clean_methodology is not null
        or r.negotiated_dollar is not null
        or r.negotiated_percentage is not null
        or {{ hpt_clean_display_text('r.negotiated_algorithm') }} is not null
    )
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
    and not exists (
        select 1
        from {{ hpt_scoped_ref('val__payer_rate_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
            and rej.source_rate_ordinal = r.source_rate_ordinal
    )
