select
    attempts.*,
    runs.command as run_command,
    runs.terminal_status as run_terminal_status
from {{ ref('stg_audit__attempts') }} attempts
inner join {{ ref('audit__runs') }} runs
    on attempts.run_id = runs.run_id
