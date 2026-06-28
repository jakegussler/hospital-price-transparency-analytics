-- Thin conformed service-code (code-cohort) dimension.
-- Grain: one row per (canonical_code_system, match_code) observed among
-- cross-hospital-comparable codes. service_code_key is the conformed cohort key
-- the code bridge and the comparison marts join on.
--
-- Full-refresh table read UNscoped (plain ref) from slv_core__charge_item_codes:
-- a conformed dimension must span every snapshot, so it is excluded from the
-- snapshot prune and never added to hpt_snapshot_grained_incremental_models().
--
-- The conformed key + the SEAM where external-data-enrichment attaches code
-- descriptions and grouper context (decision 0019). Green-light, public-domain
-- descriptions (MS-DRG today; HCPCS/APC next) join from
-- slv_core__billing_code_descriptions; licensed systems (CPT/CDT) stay
-- description-null until a license is acquired. has_code_description gates the
-- legible subset for the marts/analyses without reshaping them.
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
),

-- One description per (system, code): the most recent loaded edition. The
-- conformed dimension spans all snapshots, so it carries the latest edition's
-- description rather than a per-snapshot as-of join (a documented v1 simplification).
descriptions as (
    select
        canonical_code_system,
        match_code,
        code_description,
        code_edition,
        code_description_source,
        code_description_license,
        relative_weight,
        mdc,
        drg_type
    from {{ ref('slv_core__billing_code_descriptions') }}
    qualify row_number() over (
        partition by canonical_code_system, match_code
        order by code_edition desc
    ) = 1
),

joined as (
    select
        comparable_cohorts.canonical_code_system,
        comparable_cohorts.match_code,
        comparable_cohorts.code_is_specific,
        comparable_cohorts.code_cross_hospital_comparable,
        descriptions.code_description,
        descriptions.code_edition as code_description_edition,
        descriptions.code_description_source,
        descriptions.code_description_license,
        descriptions.relative_weight,
        descriptions.mdc as ms_drg_mdc,
        descriptions.drg_type as ms_drg_type
    from comparable_cohorts
    left join descriptions
        on comparable_cohorts.canonical_code_system = descriptions.canonical_code_system
        and comparable_cohorts.match_code = descriptions.match_code
)

select
    {{ hpt_surrogate_key(['canonical_code_system', 'match_code']) }} as service_code_key,
    canonical_code_system,
    match_code,
    code_is_specific,
    code_cross_hospital_comparable,
    code_description,
    code_description_edition,
    code_description_source,
    code_description_license,
    relative_weight,
    ms_drg_mdc,
    ms_drg_type,
    (code_description is not null) as has_code_description
from joined
