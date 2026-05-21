select
    hospital_id,
    canonical_hospital_name,
    {{ hpt_clean_text('canonical_hospital_name') }} as clean_canonical_hospital_name,
    canonical_state,
    hospital_type,
    health_system,
    mrf_url,
    expected_format
from {{ ref('hospitals') }}
