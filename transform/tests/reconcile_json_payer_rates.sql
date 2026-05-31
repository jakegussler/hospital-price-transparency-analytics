with expected as (
    select
        pi.snapshot_id,
        count(*) as expected_rows
    from {{ ref('stg_bronze__payers_information') }} pi
    inner join {{ ref('stg_bronze__standard_charges') }} sc
        on pi.snapshot_id = sc.snapshot_id
        and pi.standard_charge_id = sc.standard_charge_id
    where not exists (
            select 1
            from {{ ref('val__snapshot_rejections') }} r
            where r.snapshot_id = pi.snapshot_id
        )
        and not exists (
            select 1
            from {{ ref('val__charge_item_rejections') }} r
            where r.source_format_family = 'json'
                and r.snapshot_id = sc.snapshot_id
                and r.source_charge_item_id = sc.charge_item_id
        )
        and not exists (
            select 1
            from {{ ref('val__standard_charge_rejections') }} r
            where r.source_format_family = 'json'
                and r.snapshot_id = pi.snapshot_id
                and r.source_standard_charge_id = pi.standard_charge_id
        )
        and not exists (
            select 1
            from {{ ref('val__payer_rate_rejections') }} r
            where r.source_format_family = 'json'
                and r.snapshot_id = pi.snapshot_id
                and r.source_standard_charge_id = pi.standard_charge_id
                and r.payer_ordinal = pi.payer_ordinal
        )
    group by pi.snapshot_id
),

actual as (
    select
        snapshot_id,
        count(*) as actual_rows
    from {{ ref('slv_base__payer_rates') }}
    where source_format = 'json'
    group by snapshot_id
)

select
    coalesce(expected.snapshot_id, actual.snapshot_id) as snapshot_id,
    coalesce(expected.expected_rows, 0) as expected_rows,
    coalesce(actual.actual_rows, 0) as actual_rows
from expected
full outer join actual using (snapshot_id)
where coalesce(expected.expected_rows, 0) <> coalesce(actual.actual_rows, 0)
