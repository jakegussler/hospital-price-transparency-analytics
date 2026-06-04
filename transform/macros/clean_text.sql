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

{% macro hpt_title_case_text(expression) -%}
    {%- set cleaned = hpt_clean_text(expression) -%}
    case
        when {{ cleaned }} is null then null
        else array_to_string(
            list_transform(
                string_split({{ cleaned }}, ' '),
                word -> upper(substr(word, 1, 1)) || lower(substr(word, 2))
            ),
            ' '
        )
    end
{%- endmacro %}
