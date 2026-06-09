{% macro hpt_trimmed_text(expression) -%}
    {%- set trimmed -%}
        trim(cast({{ expression }} as varchar))
    {%- endset -%}

    case
        when {{ expression }} is null then null
        when {{ trimmed }} = '' then null
        else {{ trimmed }}
    end
{%- endmacro %}

{% macro hpt_normalize_text(expression, lowercase=true) -%}
    {%- set trimmed = hpt_trimmed_text(expression) -%}
    {%- set normalized -%}
        regexp_replace(
            {{ trimmed }},
            '\s+',
            ' ',
            'g'
        )
    {%- endset -%}

    case
        when {{ trimmed }} is null then null
        {%- if lowercase %}
        else lower({{ normalized }})
        {%- else %}
        else {{ normalized }}
        {%- endif %}
    end
{%- endmacro %}

{% macro hpt_nullify_sentinel_text(expression, lowercase=true) -%}
    {%- set normalized = hpt_normalize_text(expression, lowercase=false) -%}

    case
        when {{ normalized }} is null then null
        when lower({{ normalized }}) in (
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
        else lower({{ normalized }})
        {%- else %}
        else {{ normalized }}
        {%- endif %}
    end
{%- endmacro %}

{% macro hpt_title_case_text(expression) -%}
    {%- set cleaned = hpt_normalize_text(expression) -%}
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
