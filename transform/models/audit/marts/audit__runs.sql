with ranked as (
    select
        *,
        row_number() over (
            partition by run_id
            order by
                (state = 'completed') desc,
                coalesce(ended_at, started_at) desc
        ) as state_rank
    from {{ ref('stg_audit__run_events') }}
)

select
    run_id,
    run_date,
    command,
    requested_targets,
    options,
    started_at,
    ended_at,
    elapsed_s,
    exit_code,
    case
        when state = 'completed' then terminal_status
        else 'running_or_interrupted'
    end as terminal_status,
    target_count,
    success_count,
    failure_count,
    failure_category,
    failure_message,
    stdout_log_path,
    json_log_path
from ranked
where state_rank = 1
