{% macro hpt_scoped_ref(model_name) -%}
(
    select *
    from {{ ref(model_name) }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)
{%- endmacro %}


{% macro hpt_scoped_source(source_name, table_name) -%}
(
    select *
    from {{ source(source_name, table_name) }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
)
{%- endmacro %}
