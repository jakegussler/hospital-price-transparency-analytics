select
    attempt_id,
    stage_name
from {{ ref('audit__attempt_stages') }}
group by attempt_id, stage_name
having count(*) > 1
