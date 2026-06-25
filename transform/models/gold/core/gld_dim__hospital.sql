-- Conformed hospital dimension. Grain: one row per hospital_id.
--
-- Full-refresh table read UNscoped (plain ref) from the registry-backed
-- slv_base__hospitals, mirroring that model's precedent: a conformed dimension
-- must span every snapshot, so a snapshot-scoped run must never shrink it. It is
-- therefore excluded from the snapshot prune and must never be added to
-- hpt_snapshot_grained_incremental_models().
--
-- SCD type 1: registry-backed, no history retained. Materialization (table,
-- incremental_strategy null, schema gold) is set in dbt_project.yml.
select
    hospital_id,
    canonical_hospital_name,
    clean_canonical_hospital_name,
    canonical_state,
    canonical_state_name,
    canonical_state_type,
    canonical_census_region,
    canonical_census_division,
    hospital_type,
    health_system,
    expected_format,
    mrf_url
from {{ ref('slv_base__hospitals') }}
