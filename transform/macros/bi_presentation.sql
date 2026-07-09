{#-
    BI presentation helpers shared by the gld_bi__* marts.

    These are display/navigation fields, not comparability logic: the slug is a
    stable URL identifier for service pages, and description availability
    explains WHY a code has no description (license-restricted reference data
    vs. reference data not yet loaded) so public surfaces do not misattribute a
    licensing constraint to the hospital.
-#}

{#- URL-safe service slug, unique per (canonical_code_system, match_code)
    because both inputs come from the gld_dim__service_code grain. Uniqueness
    against normalization collisions is locked by the singular test
    gld_bi_service_slug_one_to_one.sql. -#}
{% macro hpt_service_url_slug(system_col, code_col) -%}
    trim(
        regexp_replace(
            lower({{ system_col }} || '-' || {{ code_col }}),
            '[^a-z0-9]+',
            '-',
            'g'
        ),
        '-'
    )
{%- endmacro %}


{#- Why a service code's description is (un)available. CPT and CDT are
    license-restricted code systems (decision 0019): their descriptions cannot
    be republished without a license, so their absence is not a hospital
    publishing failure. Everything else without a loaded description is
    reference data not yet loaded (MS-DRG is loaded today; HCPCS/APC next). -#}
{% macro hpt_description_availability(has_description_col, code_system_col) -%}
    case
        when coalesce({{ has_description_col }}, false) then 'available'
        when {{ code_system_col }} in ('cpt', 'cdt') then 'license_restricted'
        else 'not_loaded'
    end
{%- endmacro %}
