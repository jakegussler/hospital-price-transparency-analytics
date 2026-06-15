{% macro get_incremental_snapshot_replace_sql(arg_dict) -%}
    {#-
        Replace the explicitly requested snapshot batch, including replacement
        with zero rows. dbt has already built the model result in temp_relation;
        validate its scope before deleting from the accumulated target.
    -#}
    {%- set unique_key = arg_dict['unique_key'] -%}
    {%- if unique_key != 'snapshot_id' -%}
        {{ exceptions.raise_compiler_error(
            "snapshot_replace requires unique_key='snapshot_id', got "
            ~ (unique_key | string) ~ "."
        ) }}
    {%- endif -%}

    {%- set incremental_predicates = arg_dict['incremental_predicates'] -%}
    {%- if incremental_predicates -%}
        {{ exceptions.raise_compiler_error(
            "snapshot_replace does not accept incremental_predicates because "
            ~ "they could weaken the requested snapshot replacement."
        ) }}
    {%- endif -%}

    {%- set snapshot_ids = hpt_normalize_snapshot_id_list(var('snapshot_ids', [])) -%}
    {%- set requested_source_predicate = hpt_snapshot_id_predicate(
        snapshot_ids,
        'DBT_INTERNAL_SOURCE.snapshot_id',
        require_ids=true,
        operation='snapshot_replace'
    ) -%}
    {%- set requested_target_predicate = hpt_snapshot_id_predicate(
        snapshot_ids,
        'snapshot_id',
        require_ids=true,
        operation='snapshot_replace'
    ) -%}

    select error(
        'snapshot_replace model output contains a null or unrequested snapshot_id'
    )
    from {{ arg_dict['temp_relation'] }} as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.snapshot_id is null
        or not ({{ requested_source_predicate }})
    limit 1;

    delete from {{ arg_dict['target_relation'] }}
    where {{ requested_target_predicate }};

    {{ get_insert_into_sql(
        arg_dict['target_relation'],
        arg_dict['temp_relation'],
        arg_dict['dest_columns']
    ) }}
{%- endmacro %}
