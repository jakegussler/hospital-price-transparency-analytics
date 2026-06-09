select
    h.hospital_id,
    h.canonical_hospital_name,
    {{ hpt_normalize_text('h.canonical_hospital_name') }} as clean_canonical_hospital_name,
    h.canonical_state,
    states.state_name as canonical_state_name,
    states.state_type as canonical_state_type,
    states.census_region as canonical_census_region,
    states.census_division as canonical_census_division,
    h.hospital_type,
    h.health_system,
    h.mrf_url,
    h.expected_format
from {{ ref('hospitals') }} h
left join {{ ref('states') }} states
    on h.canonical_state = states.state_code
