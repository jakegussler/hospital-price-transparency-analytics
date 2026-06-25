-- Conformed snapshot dimension. Grain: one row per snapshot_id.
--
-- Holds the time / lineage / currentness attributes so the rate-observation fact
-- stays lean. Read UNscoped (plain ref) from slv_base__hospital_snapshots: a
-- conformed dimension must span every snapshot even on a snapshot-scoped run, so
-- it is a full-refresh table excluded from the snapshot prune and never added to
-- hpt_snapshot_grained_incremental_models().
--
-- In v1 (single snapshot per hospital under current_only retention) this
-- dimension also carries the date attributes a separate gld_dim__date would hold
-- in a history-enabled build; gld_dim__date is deferred.
with snapshots as (
    select
        snapshot_id,
        hospital_id,
        source_format,
        is_current_snapshot,
        valid_from,
        valid_to,
        published_last_updated_on,
        ingested_at,
        schema_version,
        source_url,
        source_file_name,
        file_hash
    from {{ ref('slv_base__hospital_snapshots') }}
),

aged as (
    select
        *,
        case
            when published_last_updated_on is null then null
            else date_diff('day', cast(published_last_updated_on as date), current_date)
        end as snapshot_age_days
    from snapshots
)

select
    snapshot_id,
    hospital_id,
    source_format,
    is_current_snapshot,
    valid_from,
    valid_to,
    published_last_updated_on,
    ingested_at,
    schema_version,
    source_url,
    source_file_name,
    file_hash,
    snapshot_age_days,
    case
        when snapshot_age_days is null then 'unknown'
        when snapshot_age_days <= 90 then '<=90d'
        when snapshot_age_days <= 180 then '<=180d'
        when snapshot_age_days <= 365 then '<=365d'
        else '>365d'
    end as freshness_bucket
from aged
