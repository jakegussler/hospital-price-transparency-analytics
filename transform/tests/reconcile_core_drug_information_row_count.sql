with base_counts as (
    select count(*) as row_count
    from {{ hpt_scoped_ref('slv_base__drug_information') }}
),

core_counts as (
    select count(*) as row_count
    from {{ hpt_scoped_ref('slv_core__drug_information') }}
)

select
    base_counts.row_count as base_row_count,
    core_counts.row_count as core_row_count
from base_counts
cross join core_counts
where base_counts.row_count <> core_counts.row_count
