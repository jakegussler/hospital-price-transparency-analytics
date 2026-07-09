-- Contract guard: the comparability funnel stages are cumulative gates, so
-- each stage's row_count must never exceed the previous stage's within one
-- scope/hospital funnel. A violation means a stage condition stopped being a
-- superset of the next one and the public funnel visual would be incoherent.
with staged as (
    select
        scope_level,
        hospital_id,
        stage_index,
        row_count,
        lag(row_count) over (
            partition by scope_level, hospital_id
            order by stage_index
        ) as previous_row_count
    from {{ ref('gld_bi__comparability_funnel') }}
)

select *
from staged
where previous_row_count is not null
    and row_count > previous_row_count
