select
    {{ hpt_surrogate_key(['n.snapshot_id', 'n.npi_ordinal']) }} as silver_type2_npi_id,
    n.snapshot_id,
    s.hospital_id,
    s.source_format,
    n.npi_ordinal,
    n.raw_npi,
    n.clean_npi
from {{ ref('stg_bronze__type2_npi') }} n
inner join {{ ref('slv_base__hospital_snapshots') }} s
    on n.snapshot_id = s.snapshot_id
where not exists (
    select 1
    from {{ ref('val__npi_rejections') }} r
    where r.snapshot_id = n.snapshot_id
        and r.npi_ordinal = n.npi_ordinal
)
