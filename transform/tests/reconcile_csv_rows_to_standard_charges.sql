select
    r.snapshot_id,
    r.row_ordinal
from {{ ref('stg_bronze__csv_charge_rows') }} r
left join {{ ref('slv_base__payer_rates') }} pr
    on r.snapshot_id = pr.snapshot_id
    and r.row_ordinal = pr.source_row_ordinal
    and r.source_rate_ordinal = pr.source_rate_ordinal
left join {{ ref('slv_base__standard_charges') }} standard_charges
    on pr.silver_standard_charge_id = standard_charges.silver_standard_charge_id
where standard_charges.silver_standard_charge_id is null
    and not exists (
        select 1
        from {{ ref('val__snapshot_rejections') }} rej
        where rej.snapshot_id = r.snapshot_id
    )
    and not exists (
        select 1
        from {{ ref('val__charge_item_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
    )
    and not exists (
        select 1
        from {{ ref('val__standard_charge_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
    )
    and not exists (
        select 1
        from {{ ref('val__payer_rate_rejections') }} rej
        where rej.source_format_family = 'csv'
            and rej.snapshot_id = r.snapshot_id
            and rej.row_ordinal = r.row_ordinal
            and rej.source_rate_ordinal = r.source_rate_ordinal
    )
