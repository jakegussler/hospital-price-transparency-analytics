{% macro hpt_methodology_values() -%}
    {{ return([
        'case rate',
        'fee schedule',
        'percent of total billed charges',
        'per diem',
        'other'
    ]) }}
{%- endmacro %}

{% macro hpt_methodology_values_sql() -%}
(
    {%- for value in hpt_methodology_values() %}
    '{{ value }}'{{ "," if not loop.last }}
    {%- endfor %}
)
{%- endmacro %}

{% macro hpt_canonical_methodology(expression) -%}
    {# Placeholder for a future methodology alias map. For now, only exact CMS
       display values are canonicalized. #}
    case
        when {{ hpt_clean_text(expression) }} in {{ hpt_methodology_values_sql() }}
            then {{ hpt_clean_text(expression) }}
        else null
    end
{%- endmacro %}

{% macro hpt_count_min(expression) -%}
    case
        when {{ hpt_clean_display_text(expression) }} = '0' then 0
        when {{ hpt_clean_display_text(expression) }} = '1 through 10' then 1
        when regexp_matches(
            {{ hpt_clean_display_text(expression) }},
            '^(1[1-9]|[2-9][0-9]+|[1-9][0-9]{2,})$'
        ) then cast({{ hpt_clean_display_text(expression) }} as integer)
        else null
    end
{%- endmacro %}

{% macro hpt_count_max(expression) -%}
    case
        when {{ hpt_clean_display_text(expression) }} = '0' then 0
        when {{ hpt_clean_display_text(expression) }} = '1 through 10' then 10
        when regexp_matches(
            {{ hpt_clean_display_text(expression) }},
            '^(1[1-9]|[2-9][0-9]+|[1-9][0-9]{2,})$'
        ) then cast({{ hpt_clean_display_text(expression) }} as integer)
        else null
    end
{%- endmacro %}
