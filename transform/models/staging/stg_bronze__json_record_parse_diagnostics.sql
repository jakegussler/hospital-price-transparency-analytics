{% if hpt_has_bronze_files('json_record_parse_diagnostics') %}
    select
        snapshot_id,
        section,
        cast(record_ordinal as integer) as record_ordinal,
        reported_schema_version,
        reported_schema_family,
        accepted_schema_family,
        accepted_schema_version,
        cast(schema_version_mismatch as boolean) as schema_version_mismatch,
        attempted_schema_families,
        cast(failure_count as integer) as failure_count,
        error_summary,
        final_status,
        {{ hpt_safe_timestamp('diagnosed_at') }} as diagnosed_at
    from {{ source('bronze', 'json_record_parse_diagnostics') }}
    where 1 = 1
        {{ hpt_snapshot_filter() }}
{% else %}
    select
        cast(null as varchar) as snapshot_id,
        cast(null as varchar) as section,
        cast(null as integer) as record_ordinal,
        cast(null as varchar) as reported_schema_version,
        cast(null as varchar) as reported_schema_family,
        cast(null as varchar) as accepted_schema_family,
        cast(null as varchar) as accepted_schema_version,
        cast(null as boolean) as schema_version_mismatch,
        cast(null as varchar) as attempted_schema_families,
        cast(null as integer) as failure_count,
        cast(null as varchar) as error_summary,
        cast(null as varchar) as final_status,
        cast(null as timestamp) as diagnosed_at
    where false
{% endif %}
