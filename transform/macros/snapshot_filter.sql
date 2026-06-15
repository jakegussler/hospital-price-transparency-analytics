{% macro hpt_normalize_snapshot_id_list(snapshot_ids) -%}
    {#- Coerce a comma-separated string or list into a clean list of snapshot ids. -#}
    {%- if snapshot_ids is none -%}
        {{ return([]) }}
    {%- endif -%}
    {%- set raw = snapshot_ids.split(',') if snapshot_ids is string else snapshot_ids -%}
    {%- set normalized = [] -%}
    {%- for snapshot_id in raw -%}
        {%- set cleaned = snapshot_id | trim -%}
        {%- if cleaned -%}
            {%- do normalized.append(cleaned) -%}
        {%- endif -%}
    {%- endfor -%}
    {{ return(normalized) }}
{%- endmacro %}


{% macro hpt_snapshot_id_predicate(
    snapshot_ids=None,
    column_name='snapshot_id',
    require_ids=false,
    operation='snapshot predicate'
) -%}
    {#- Render a safely quoted snapshot-id predicate, failing closed when empty. -#}
    {%- set raw_ids = var('snapshot_ids', []) if snapshot_ids is none else snapshot_ids -%}
    {%- set ids = hpt_normalize_snapshot_id_list(raw_ids) -%}
    {%- if require_ids and ids | length == 0 -%}
        {{ exceptions.raise_compiler_error(
            operation ~ " requires at least one snapshot_id. Refusing to run "
            ~ "an unscoped operation."
        ) }}
    {%- endif -%}
    {%- if ids | length == 0 -%}
        {{ return('1 = 0') }}
    {%- endif -%}

    {%- set quoted = [] -%}
    {%- for snapshot_id in ids -%}
        {%- do quoted.append(dbt.string_literal(dbt.escape_single_quotes(snapshot_id))) -%}
    {%- endfor -%}
    {{ return(column_name ~ ' in (' ~ quoted | join(', ') ~ ')') }}
{%- endmacro %}


{% macro hpt_snapshot_filter(table_alias=None) -%}
    {%- set snapshot_ids = hpt_normalize_snapshot_id_list(var('snapshot_ids', [])) -%}
    {%- if snapshot_ids | length > 0 -%}
        and {{ hpt_snapshot_id_predicate(
            snapshot_ids,
            (table_alias ~ '.' if table_alias else '') ~ 'snapshot_id'
        ) }}
    {%- endif -%}
{%- endmacro %}
