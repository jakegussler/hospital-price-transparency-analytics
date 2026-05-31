with bronze as (
    select s.snapshot_id
    from {{ ref('stg_bronze__hospital_mrf_snapshots') }} s
    where not exists (
        select 1
        from {{ ref('val__snapshot_rejections') }} r
        where r.snapshot_id = s.snapshot_id
    )
),

silver as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
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
