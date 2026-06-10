select
    snapshot_id,
    cast(location_ordinal as integer) as location_ordinal,
    location_name as raw_location_name,
    {{ hpt_clean_text('location_name') }} as clean_location_name,
    hospital_address as raw_hospital_address,
    {{ hpt_clean_display_text('hospital_address') }} as clean_hospital_address
from {{ source('bronze', 'hospital_locations') }}
