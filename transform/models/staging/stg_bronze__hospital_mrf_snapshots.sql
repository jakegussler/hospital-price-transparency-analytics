select
    snapshot_id,
    hospital_id,
    reported_hospital_name as raw_reported_hospital_name,
    {{ hpt_clean_text('reported_hospital_name') }} as clean_reported_hospital_name,
    source_url,
    source_file_name,
    {{ hpt_clean_text('source_format') }} as source_format,
    file_hash,
    ingested_at as raw_ingested_at,
    {{ hpt_safe_timestamp('ingested_at') }} as ingested_at,
    published_last_updated_on as raw_published_last_updated_on,
    {{ hpt_safe_date('published_last_updated_on') }} as published_last_updated_on,
    schema_version,
    is_current_snapshot,
    valid_from as raw_valid_from,
    {{ hpt_safe_timestamp('valid_from') }} as valid_from,
    valid_to as raw_valid_to,
    {{ hpt_safe_timestamp('valid_to') }} as valid_to,
    attestation,
    confirm_attestation,
    attester_name,
    {{ hpt_bronze_column_or_null('hospital_mrf_snapshots', 'affirmation') }}
        as affirmation,
    {{ hpt_bronze_column_or_null('hospital_mrf_snapshots', 'confirm_affirmation') }}
        as confirm_affirmation,
    reported_state,
    license_number
from {{ hpt_staging_source(source('bronze', 'hospital_mrf_snapshots')) }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
