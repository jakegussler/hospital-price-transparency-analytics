with bronze as (
    select snapshot_id
    from {{ ref('stg_bronze__hospital_mrf_snapshots') }}
),

silver as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)

select bronze.snapshot_id
from bronze
left join silver using (snapshot_id)
where silver.snapshot_id is null

union all

select silver.snapshot_id
from silver
left join bronze using (snapshot_id)
where bronze.snapshot_id is null
