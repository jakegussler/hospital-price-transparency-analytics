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
