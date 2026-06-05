-- Fails if any hospital resolves to more than one current snapshot.
--
-- Currentness is derived (not stored) by valid_from recency in
-- hpt_resolved_snapshot_state_sql, which reads the full, unscoped Bronze set.
-- This guards against the historical bug where, after a re-download, multiple
-- Bronze hospital_mrf_snapshots rows could each carry is_current_snapshot = true
-- for the same hospital and defeat current_only retention.
with resolved as (
    {{ hpt_resolved_snapshot_state_sql() }}
)

select
    hospital_id,
    count(*) as current_count
from resolved
where is_current_snapshot = true
group by hospital_id
having count(*) > 1
