{% macro hpt_clean_text(expression, lowercase=true) -%}
    {%- set cleaned -%}
        regexp_replace(
            trim(cast({{ expression }} as varchar)),
            '\\s+',
            ' ',
            'g'
        )
    {%- endset -%}

    case
        when {{ expression }} is null then null
        when lower({{ cleaned }}) in (
            '',
            'null',
            'none',
            'n/a',
            'na',
            'not applicable',
            'not available',
            'unknown',
            '-'
        ) then null
        {%- if lowercase %}
        else lower({{ cleaned }})
        {%- else %}
        else {{ cleaned }}
        {%- endif %}
    end
{%- endmacro %}

{% macro hpt_clean_display_text(expression) -%}
    {{ hpt_clean_text(expression, lowercase=false) }}
{%- endmacro %}
