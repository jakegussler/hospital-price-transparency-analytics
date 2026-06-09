select
    snapshot_id,
    cast(location_ordinal as integer) as location_ordinal,
    location_name as raw_location_name,
    {{ hpt_normalize_text('location_name') }} as clean_location_name,
    hospital_address as raw_hospital_address,
    {{ hpt_trimmed_text('hospital_address') }} as clean_hospital_address
from {{ source('bronze', 'hospital_locations') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
