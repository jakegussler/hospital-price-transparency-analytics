-- One row per dbt node per invocation, enriched with the parent attempt's
-- command/selector context and the run's terminal status. row_count_semantics
-- documents how to read rows_affected, which means different things per
-- materialization (a full table rebuild count vs. an incremental delta vs. n/a
-- for views vs. test-failure rows), so downstream consumers do not sum across
-- incompatible grains.
select
    nodes.run_id,
    nodes.run_date,
    nodes.attempt_id,
    attempts.attempt_ordinal,
    attempts.status as attempt_status,
    nodes.node_unique_id,
    nodes.node_name,
    nodes.resource_type,
    nodes.package_name,
    nodes.materialization,
    nodes.node_schema,
    nodes.tags,
    nodes.node_status,
    nodes.message,
    nodes.test_failures,
    nodes.execution_time_s,
    nodes.compile_elapsed_s,
    nodes.execute_elapsed_s,
    nodes.started_at,
    nodes.ended_at,
    nodes.rows_affected,
    case
        when nodes.resource_type = 'test' then 'use_test_failures'
        when nodes.materialization = 'view' then 'not_applicable'
        when nodes.materialization = 'incremental' then 'rows_written_this_run'
        when nodes.materialization = 'table' then 'rebuilt_table_rows'
        when nodes.resource_type = 'seed' then 'rows_seeded'
        else 'unknown'
    end as row_count_semantics,
    nodes.adapter_code,
    nodes.thread_id,
    nodes.dbt_command,
    nodes.dbt_selector,
    nodes.dbt_full_refresh,
    nodes.snapshot_ids,
    nodes.snapshot_count,
    runs.command as run_command,
    runs.terminal_status as run_terminal_status
from {{ ref('stg_audit__node_results') }} nodes
inner join {{ ref('audit__runs') }} runs
    on nodes.run_id = runs.run_id
left join {{ ref('audit__attempts') }} attempts
    on nodes.attempt_id = attempts.attempt_id
