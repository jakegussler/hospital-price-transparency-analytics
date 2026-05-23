with expected as (
    select
        pi.snapshot_id,
        count(*) as expected_rows
    from {{ ref('stg_bronze__payers_information') }} pi
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
