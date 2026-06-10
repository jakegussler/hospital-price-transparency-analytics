{% if hpt_has_bronze_files('json_record_parse_diagnostics') %}
    select
        snapshot_id,
        section,
        cast(record_ordinal as integer) as record_ordinal,
        reported_schema_version,
        reported_schema_family,
        parser_schema_family,
        parser_schema_version,
        cast(schema_version_mismatch as boolean) as schema_version_mismatch,
        cast(conflicting_version_signals as boolean) as conflicting_version_signals,
        cast(failure_count as integer) as failure_count,
        error_summary,
        {{ hpt_safe_timestamp('diagnosed_at') }} as diagnosed_at
    from {{ source('bronze', 'json_record_parse_diagnostics') }}
{% else %}
    select
        cast(null as varchar) as snapshot_id,
        cast(null as varchar) as section,
        cast(null as integer) as record_ordinal,
        cast(null as varchar) as reported_schema_version,
        cast(null as varchar) as reported_schema_family,
        cast(null as varchar) as parser_schema_family,
        cast(null as varchar) as parser_schema_version,
        cast(null as boolean) as schema_version_mismatch,
        cast(null as boolean) as conflicting_version_signals,
        cast(null as integer) as failure_count,
        cast(null as varchar) as error_summary,
        cast(null as timestamp) as diagnosed_at
    where false
{% endif %}
