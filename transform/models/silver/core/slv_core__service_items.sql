{{ config(materialized='table') }}

-- Within-hospital, cross-snapshot service-item dimension: one row per
-- service_item_id, aggregated across every retained snapshot of
-- slv_core__charge_items. Reads its inputs UNscoped on purpose: this is a
-- full rebuild over the retained corpus, and a snapshot-scoped run must still
-- see every retained snapshot or the rebuild would shrink the dimension to
-- the scoped snapshot. For the same reason it is a table, not a
-- snapshot-keyed incremental, and it must never be added to
-- hpt_snapshot_grained_incremental_models(). Under the default current_only
-- retention every hospital holds one snapshot, so snapshot_count = 1
-- everywhere; continuity tracking becomes meaningful only under all_snapshots
-- retention with multi-snapshot ingestion.
with items as (
    select
        charge_items.service_item_id,
        charge_items.hospital_id,
        charge_items.snapshot_id,
        charge_items.silver_charge_item_id,
        charge_items.clean_description,
        charge_items.service_item_identity_basis,
        charge_items.service_item_identity_confidence,
        charge_items.code_signature_specific,
        charge_items.code_signature_all,
        charge_items.drug_signature,
        snapshots.valid_from
    from {{ ref('slv_core__charge_items') }} charge_items
    left join {{ ref('slv_base__hospital_snapshots') }} snapshots
        on charge_items.snapshot_id = snapshots.snapshot_id
),

ranked as (
    select
        *,
        row_number() over (
            partition by service_item_id
            order by
                valid_from asc nulls last,
                snapshot_id asc,
                clean_description asc,
                silver_charge_item_id asc
        ) as first_seen_rank,
        row_number() over (
            partition by service_item_id
            order by
                valid_from desc nulls last,
                snapshot_id desc,
                clean_description asc,
                silver_charge_item_id asc
        ) as last_seen_rank
    from items
)

select
    service_item_id,
    hospital_id,
    max(case when last_seen_rank = 1 then service_item_identity_basis end)
        as service_item_identity_basis,
    max(case when last_seen_rank = 1 then service_item_identity_confidence end)
        as service_item_identity_confidence,
    max(case when last_seen_rank = 1 then code_signature_specific end)
        as code_signature_specific,
    max(case when last_seen_rank = 1 then code_signature_all end)
        as code_signature_all,
    max(case when last_seen_rank = 1 then drug_signature end)
        as drug_signature,
    max(case when last_seen_rank = 1 then clean_description end)
        as representative_clean_description,
    max(case when first_seen_rank = 1 then snapshot_id end)
        as first_seen_snapshot_id,
    max(case when first_seen_rank = 1 then valid_from end)
        as first_seen_date,
    max(case when last_seen_rank = 1 then snapshot_id end)
        as last_seen_snapshot_id,
    max(case when last_seen_rank = 1 then valid_from end)
        as last_seen_date,
    count(distinct snapshot_id) as snapshot_count,
    count(distinct silver_charge_item_id) as source_item_count,
    count(distinct clean_description) as distinct_description_count
from ranked
group by service_item_id, hospital_id
