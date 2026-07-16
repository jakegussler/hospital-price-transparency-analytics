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


{#- URL-safe exact-context slug (decision 0021): the durable link target for one
    methodology-specific comparison context. Human-scannable prefix (service slug,
    public price-type word, methodology when applicable) plus a 10-char prefix of
    service_context_key that disambiguates setting/billing/modifier/drug-unit
    variants. 1:1 with service_context_key, locked by the singular test
    gld_bi_context_slug_one_to_one.sql. -#}
{% macro hpt_service_context_url_slug(
    service_url_slug_col, amount_kind_col, comparison_methodology_col, context_key_col
) -%}
    trim(
        regexp_replace(
            lower(
                {{ service_url_slug_col }}
                || '-' || case {{ amount_kind_col }}
                    when 'gross_charge' then 'list'
                    when 'discounted_cash' then 'cash'
                    when 'negotiated_dollar' then 'negotiated'
                    else {{ amount_kind_col }}
                end
                || case
                    when {{ comparison_methodology_col }} <> 'not applicable'
                        then '-' || {{ comparison_methodology_col }}
                    else ''
                end
                || '-' || substr({{ context_key_col }}, 1, 10)
            ),
            '[^a-z0-9]+',
            '-',
            'g'
        ),
        '-'
    )
{%- endmacro %}


{#- Public display label for comparison_methodology (decision 0021). The label
    must make the payment unit unmistakable — a per-diem is a DAILY payment, not
    an episode price. -#}
{% macro hpt_comparison_methodology_display_label(methodology_col) -%}
    case {{ methodology_col }}
        when 'fee schedule' then 'Fee schedule (per item/service)'
        when 'case rate' then 'Case rate (per episode)'
        when 'per diem' then 'Per diem (per day)'
        when 'not applicable' then 'Not applicable'
        else {{ methodology_col }}
    end
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
