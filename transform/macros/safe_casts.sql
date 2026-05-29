{% macro hpt_safe_date(expression) -%}
    try_cast({{ hpt_clean_display_text(expression) }} as date)
{%- endmacro %}

{% macro hpt_safe_timestamp(expression) -%}
    try_cast({{ hpt_clean_display_text(expression) }} as timestamp)
{%- endmacro %}

{% macro hpt_safe_double(expression) -%}
    try_cast({{ hpt_clean_display_text(expression) }} as double)
{%- endmacro %}

{% macro hpt_safe_decimal(expression, precision=18, scale=4) -%}
    try_cast({{ hpt_clean_display_text(expression) }} as decimal({{ precision }}, {{ scale }}))
{%- endmacro %}

{% macro hpt_safe_bigint(expression) -%}
    try_cast({{ hpt_clean_display_text(expression) }} as bigint)
{%- endmacro %}
