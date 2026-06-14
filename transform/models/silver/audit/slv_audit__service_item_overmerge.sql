-- Over-merge findings for the deterministic service-item identity: ranked
-- service_item_ids whose key absorbs more than one description or source item,
-- filtered to specific_code basis where breadth would be a signature
-- regression rather than expected categorical spread. Cross-snapshot
-- description drift is the design working as intended, so the load-bearing
-- signal is the within-snapshot spread. Findings for humans to read, not a
-- review queue for humans to approve.
with within_snapshot_spread as (
    select
        service_item_id,
        max(distinct_description_count) as max_snapshot_distinct_descriptions,
        max(source_item_count) as max_snapshot_source_items
    from (
        select
            service_item_id,
            snapshot_id,
            count(distinct clean_description) as distinct_description_count,
            count(distinct silver_charge_item_id) as source_item_count
        from {{ ref('slv_core__charge_items') }}
        group by service_item_id, snapshot_id
    ) per_snapshot
    group by service_item_id
)

select
    service_items.service_item_id,
    service_items.hospital_id,
    service_items.service_item_identity_basis,
    service_items.representative_clean_description,
    within_snapshot_spread.max_snapshot_distinct_descriptions,
    within_snapshot_spread.max_snapshot_source_items,
    service_items.distinct_description_count,
    service_items.source_item_count,
    service_items.snapshot_count
from {{ ref('slv_core__service_items') }} service_items
inner join within_snapshot_spread
    on service_items.service_item_id = within_snapshot_spread.service_item_id
where service_items.service_item_identity_basis = 'specific_code'
    and (
        within_snapshot_spread.max_snapshot_distinct_descriptions > 1
        or within_snapshot_spread.max_snapshot_source_items > 1
    )
order by
    within_snapshot_spread.max_snapshot_distinct_descriptions desc,
    service_items.distinct_description_count desc,
    service_items.source_item_count desc,
    service_items.service_item_id
