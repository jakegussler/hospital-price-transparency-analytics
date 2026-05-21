select
    {{ hpt_surrogate_key(['l.snapshot_id', 'l.location_ordinal']) }} as silver_hospital_location_id,
    l.snapshot_id,
    s.hospital_id,
    s.source_format,
    l.location_ordinal,
    l.raw_location_name,
    l.clean_location_name,
    l.raw_hospital_address,
    l.clean_hospital_address
from {{ ref('stg_bronze__hospital_locations') }} l
inner join {{ ref('slv_base__hospital_snapshots') }} s
    on l.snapshot_id = s.snapshot_id
