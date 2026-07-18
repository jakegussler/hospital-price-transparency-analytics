-- Authoritative current-snapshot projection of the retained-snapshot comparison
-- spine. Currentness is joined from gld_dim__snapshot rather than trusted from
-- the denormalized fact/spine flag, which can become stale when a newer snapshot
-- supersedes an already-materialized historical partition.

select
    spine.* exclude (is_current_snapshot, not_current_snapshot),
    snapshots.is_current_snapshot,
    (not snapshots.is_current_snapshot) as not_current_snapshot
from {{ ref('gld_int__service_comparison_spine') }} as spine
inner join {{ ref('gld_dim__snapshot') }} as snapshots
    on spine.snapshot_id = snapshots.snapshot_id
where snapshots.is_current_snapshot = true
