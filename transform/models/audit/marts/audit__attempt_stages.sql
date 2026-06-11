with stage_names as (
    select
        attempt_id,
        stage_name
    from {{ ref('stg_audit__attempts') }}
    cross join unnest(
        list_distinct(
            list_concat(
                map_keys(stage_statuses),
                map_keys(stage_elapsed_s)
            )
        )
    ) as stages(stage_name)
)

select
    attempts.run_id,
    attempts.run_date,
    attempts.attempt_id,
    attempts.attempt_ordinal,
    attempts.attempt_type,
    attempts.hospital_id,
    attempts.snapshot_id,
    stage_names.stage_name,
    map_extract_value(attempts.stage_statuses, stage_names.stage_name) as stage_status,
    map_extract_value(attempts.stage_elapsed_s, stage_names.stage_name) as stage_elapsed_s
from stage_names
inner join {{ ref('stg_audit__attempts') }} attempts
    on stage_names.attempt_id = attempts.attempt_id
