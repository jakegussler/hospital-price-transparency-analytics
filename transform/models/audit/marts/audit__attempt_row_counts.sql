select
    run_id,
    run_date,
    attempt_id,
    attempt_ordinal,
    attempt_type,
    hospital_id,
    snapshot_id,
    'bronze' as count_type,
    entry.key as table_name,
    entry.value as row_count
from {{ ref('stg_audit__attempts') }}
cross join unnest(map_entries(bronze_row_counts)) as counts(entry)

union all

select
    run_id,
    run_date,
    attempt_id,
    attempt_ordinal,
    attempt_type,
    hospital_id,
    snapshot_id,
    'quarantine' as count_type,
    entry.key as table_name,
    entry.value as row_count
from {{ ref('stg_audit__attempts') }}
cross join unnest(map_entries(quarantine_counts)) as counts(entry)
