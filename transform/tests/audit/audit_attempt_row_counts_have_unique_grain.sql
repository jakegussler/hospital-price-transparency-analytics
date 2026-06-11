select
    attempt_id,
    count_type,
    table_name
from {{ ref('audit__attempt_row_counts') }}
group by attempt_id, count_type, table_name
having count(*) > 1
