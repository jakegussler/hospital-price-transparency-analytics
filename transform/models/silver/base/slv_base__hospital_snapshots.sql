-- is_current_snapshot and valid_to are derived (not stored): currentness is
-- resolved by valid_from recency over the full, unscoped Bronze set. On scoped
-- incremental runs out-of-scope rows are corrected afterward by
-- hpt_sync_hospital_snapshot_current_state, which uses the same resolver.
with snapshot_state as (
    {{ hpt_resolved_snapshot_state_sql() }}
)

select
    s.snapshot_id,
    s.hospital_id,
    h.canonical_hospital_name,
    h.canonical_state,
    h.hospital_type,
    h.health_system,
    s.raw_reported_hospital_name,
    s.clean_reported_hospital_name,
    s.source_url,
    s.source_file_name,
    s.source_format,
    s.file_hash,
    s.raw_ingested_at,
    s.ingested_at,
    s.raw_published_last_updated_on,
    s.published_last_updated_on,
    s.schema_version,
    state.is_current_snapshot,
    s.raw_valid_from,
    s.valid_from,
    state.valid_to,
    s.attestation,
    s.confirm_attestation,
    s.attester_name,
    s.affirmation,
    s.confirm_affirmation,
    s.reported_state,
    s.license_number
from {{ ref('stg_bronze__hospital_mrf_snapshots') }} s
left join {{ ref('slv_base__hospitals') }} h
    on s.hospital_id = h.hospital_id
left join snapshot_state state
    on s.snapshot_id = state.snapshot_id
