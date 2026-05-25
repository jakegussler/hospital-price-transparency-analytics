{% macro hpt_has_bronze_files(table_name) -%}
    {%- if execute -%}
        {%- set bronze_root = env_var('HPT_BRONZE_ROOT', '../data/bronze') -%}
        {%- set pattern = bronze_root ~ '/' ~ table_name ~ '/**/*.parquet' -%}
        {%- set result = run_query("select count(*) as file_count from glob('" ~ pattern ~ "')") -%}
        {{ return((result.columns[0].values()[0] | int) > 0) }}
    {%- else -%}
        {{ return(true) }}
    {%- endif -%}
{%- endmacro %}

{% macro hpt_bronze_has_column(table_name, column_name) -%}
    {%- if execute -%}
        {%- if not hpt_has_bronze_files(table_name) -%}
            {{ return(false) }}
        {%- endif -%}
        {%- set bronze_root = env_var('HPT_BRONZE_ROOT', '../data/bronze') -%}
        {%- set pattern = bronze_root ~ '/' ~ table_name ~ '/**/*.parquet' -%}
        {%- set sql -%}
            describe select *
            from read_parquet('{{ pattern }}', hive_partitioning=true, union_by_name=true)
        {%- endset -%}
        {%- set result = run_query(sql) -%}
        {%- set columns = result.columns[0].values() | map('lower') | list -%}
        {{ return(column_name | lower in columns) }}
    {%- else -%}
        {{ return(true) }}
    {%- endif -%}
{%- endmacro %}

{% macro hpt_bronze_column_or_null(table_name, column_name, data_type='varchar') -%}
    {%- if hpt_bronze_has_column(table_name, column_name) -%}
        {{ column_name }}
    {%- else -%}
        cast(null as {{ data_type }})
    {%- endif -%}
{%- endmacro %}
