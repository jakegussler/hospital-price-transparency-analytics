with registry_hospitals as (
    select * from {{ ref('hospitals') }}

    {% if var('hpt_include_validation_fixtures', 'false') | lower == 'true' %}
    -- Fictional multi-snapshot validation hospitals, opt-in only. Production runs
    -- leave hpt_include_validation_fixtures false, so this dimension is exactly
    -- the registry seed. See docs/development/multi-snapshot-validation.md.
    union all
    select * from {{ ref('hospitals_validation_fixtures') }}
    {% endif %}
)

select
    h.hospital_id,
    h.canonical_hospital_name,
    {{ hpt_clean_text('h.canonical_hospital_name') }} as clean_canonical_hospital_name,
    h.canonical_state,
    states.state_name as canonical_state_name,
    states.state_type as canonical_state_type,
    states.census_region as canonical_census_region,
    states.census_division as canonical_census_division,
    h.hospital_type,
    h.health_system,
    h.mrf_url,
    h.expected_format
from registry_hospitals h
left join {{ ref('states') }} states
    on h.canonical_state = states.state_code
