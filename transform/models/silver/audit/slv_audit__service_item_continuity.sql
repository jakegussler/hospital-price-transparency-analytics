-- Cross-snapshot continuity scorecard for the deterministic service-item
-- identity (decision 0014). One row per hospital summarizing how the
-- within-hospital service_item_id behaves across the snapshots retained for
-- that hospital: how many items recur across snapshots (continuity), how many
-- first appear in the latest snapshot (minted), and how many fall out before it
-- (retired / drift-driven churn).
--
-- This is the load-bearing observability for remaining-steps.md s2.4: it is the
-- view that turns "service_item_id continuity is asserted" into "measured." It
-- is meaningful only under all_snapshots retention with multi-snapshot
-- ingestion; under the default current_only retention every hospital holds one
-- snapshot, so hospital_snapshot_count = 1, pct_items_multi_snapshot = 0, and
-- minted/retired collapse to 0 by construction.
with hospital_snapshots as (
    select
        hospital_id,
        count(distinct snapshot_id) as hospital_snapshot_count,
        max(valid_from) as latest_valid_from
    from {{ ref('slv_base__hospital_snapshots') }}
    group by hospital_id
),

service_items as (
    select
        hospital_id,
        service_item_id,
        snapshot_count,
        first_seen_date,
        last_seen_date
    from {{ ref('slv_core__service_items') }}
)

select
    service_items.hospital_id,
    hospital_snapshots.hospital_snapshot_count,
    count(*) as service_item_count,
    count(*) filter (where service_items.snapshot_count >= 2)
        as multi_snapshot_item_count,
    count(*) filter (where service_items.snapshot_count = 1)
        as single_snapshot_item_count,
    max(service_items.snapshot_count) as max_item_snapshot_count,
    round(
        count(*) filter (where service_items.snapshot_count >= 2)::double
        / nullif(count(*), 0),
        4
    ) as pct_items_multi_snapshot,
    -- Items first seen in the hospital's latest snapshot when it has history:
    -- newly introduced this period (includes drift-driven re-mints).
    count(*) filter (
        where hospital_snapshots.hospital_snapshot_count > 1
            and service_items.first_seen_date >= hospital_snapshots.latest_valid_from
    ) as minted_in_latest_item_count,
    -- Items last seen before the latest snapshot: churned out this period
    -- (includes the old id of a drift-driven re-mint).
    count(*) filter (
        where service_items.last_seen_date < hospital_snapshots.latest_valid_from
    ) as retired_before_latest_item_count
from service_items
left join hospital_snapshots
    on service_items.hospital_id = hospital_snapshots.hospital_id
group by
    service_items.hospital_id,
    hospital_snapshots.hospital_snapshot_count
order by service_item_count desc
