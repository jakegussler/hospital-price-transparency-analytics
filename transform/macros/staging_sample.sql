{% macro hpt_staging_source(relation, method=None, sample_mode=None, percentage=None, rows=None) -%}
    {%- set snapshot_ids = var('snapshot_ids', []) -%}
    {%- if snapshot_ids is string -%}
        {%- set snapshot_ids = [snapshot_ids] if snapshot_ids else [] -%}
    {%- endif -%}

    {#- Snapshot scoping takes precedence: emit the bare relation so the
        hpt_snapshot_filter() WHERE clause prunes hive partitions instead of
        the limit/sample wrapper masking it. -#}
    {%- if snapshot_ids | length > 0 -%}
        {{ relation }}
    {%- else -%}
        {%- set enabled = env_var('HPT_STAGING_FILTER_ENABLED', 'true') | lower -%}
        {%- if enabled in ['1', 'true', 't', 'yes', 'y', 'on'] -%}
            {%- set resolved_method = (
                method if method is not none else var('hpt_staging_filter_method', 'limit')
            ) | lower -%}

            {%- if resolved_method == 'sample' -%}
                {{ relation }} {{ hpt_staging_sample(sample_mode, percentage, rows) }}
            {%- elif resolved_method == 'limit' -%}
                {{ hpt_staging_limit(relation, rows) }}
            {%- else -%}
                {{ exceptions.raise_compiler_error(
                    "hpt_staging_source method must be 'limit' or 'sample', got '"
                    ~ resolved_method ~ "'."
                ) }}
            {%- endif -%}
        {%- else -%}
            {{ relation }}
        {%- endif -%}
    {%- endif -%}
{%- endmacro %}


{% macro hpt_staging_sample(mode=None, percentage=None, rows=None) -%}
    {%- set resolved_mode = (
        mode if mode is not none else var('hpt_staging_filter_sample_mode', 'rows')
    ) | lower -%}

    {%- if resolved_mode in ['percent', 'percentage', 'bernoulli', 'pct', 'p'] -%}
        {%- set resolved_percentage = percentage
            if percentage is not none
            else var('hpt_staging_filter_sample_percentage', '10')
        -%}
        using sample {{ resolved_percentage }}% (bernoulli)
    {%- elif resolved_mode in ['rows', 'row', 'reservoir'] -%}
        {%- set resolved_rows = rows
            if rows is not none
            else var('hpt_staging_filter_rows', '100000')
        -%}
        using sample {{ resolved_rows | int }} rows
    {%- else -%}
        {{ exceptions.raise_compiler_error(
            "hpt_staging_sample mode must be 'percent' or 'rows', got '"
            ~ resolved_mode ~ "'."
        ) }}
    {%- endif -%}
{%- endmacro %}


{% macro hpt_staging_limit(relation, rows=None) -%}
    {%- set resolved_rows = rows
        if rows is not none
        else var('hpt_staging_filter_rows', '100000')
    -%}
    (select * from {{ relation }} limit {{ resolved_rows | int }})
{%- endmacro %}
