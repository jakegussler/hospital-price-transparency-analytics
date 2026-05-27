with base_counts as (
    select count(*) as row_count
    from {{ ref('slv_base__payer_rates') }}
),

core_counts as (
    select count(*) as row_count
    from {{ ref('slv_core__payer_rates') }}
)

select
    base_counts.row_count as base_row_count,
    core_counts.row_count as core_row_count
from base_counts
cross join core_counts
where base_counts.row_count <> core_counts.row_count
