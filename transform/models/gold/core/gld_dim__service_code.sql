-- Thin conformed service-code (code-cohort) dimension.
-- Grain: one row per (canonical_code_system, match_code) observed among
-- cross-hospital-comparable codes. service_code_key is the conformed cohort key
-- the code bridge and the comparison marts join on.
--
-- Full-refresh table read UNscoped (plain ref) from slv_core__charge_item_codes:
-- a conformed dimension must span every snapshot, so it is excluded from the
-- snapshot prune and never added to hpt_snapshot_grained_incremental_models().
--
-- Thin on purpose: v1 ships no external code descriptions or groupers (decision
-- 0017 non-goal), so this dimension is the conformed key + the SEAM where
-- external-data-enrichment later attaches CPT/HCPCS/NDC descriptions and service
-- families without reshaping the marts.
--
-- Membership = cross-hospital-comparable codes with a non-null match_code (the
-- business key). Non-comparable systems (cdm/local) and null-keyed codes are
-- excluded here; they are still exposed downstream on the bridge, never promoted
-- to a cohort. Both code_is_specific and code_cross_hospital_comparable are pure
-- functions of canonical_code_system, so the distinct never fans out the grain.
with comparable_cohorts as (
    select distinct
        canonical_code_system,
        match_code,
        code_is_specific,
        code_cross_hospital_comparable
    from {{ ref('slv_core__charge_item_codes') }}
    where code_cross_hospital_comparable = true
        and match_code is not null
)

select
    {{ hpt_surrogate_key(['canonical_code_system', 'match_code']) }} as service_code_key,
    canonical_code_system,
    match_code,
    code_is_specific,
    code_cross_hospital_comparable
from comparable_cohorts
