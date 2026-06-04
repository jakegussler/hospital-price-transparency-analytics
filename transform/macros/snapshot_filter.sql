{% macro hpt_snapshot_filter(table_alias=None) -%}
    {%- set snapshot_ids = var('snapshot_ids', []) -%}
    {%- if snapshot_ids is string -%}
        {%- set snapshot_ids = [snapshot_ids] if snapshot_ids else [] -%}
    {%- endif -%}
    {%- if snapshot_ids | length > 0 -%}
        and {{ table_alias ~ '.' if table_alias else '' }}snapshot_id in (
            {%- for snapshot_id in snapshot_ids -%}
                '{{ snapshot_id }}'{{ ", " if not loop.last }}
            {%- endfor -%}
        )
    {%- endif -%}
{%- endmacro %}
