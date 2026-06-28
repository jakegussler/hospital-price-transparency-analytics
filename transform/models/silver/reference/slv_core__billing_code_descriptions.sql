-- Conformed code-description dimension sourced from green-light, public-domain
-- reference data (decision 0019). Grain: one row per
-- (canonical_code_system, match_code, code_edition).
--
-- This is the Silver side of the external-data-enrichment seam: it normalizes
-- every reference code system to the (canonical_code_system, match_code) keys
-- that slv_core__charge_item_codes already produces, so Gold's
-- gld_dim__service_code can attach human-readable descriptions without
-- reshaping the marts. New green-light systems (HCPCS, APC, ...) union in here.
--
-- Grouper-specific columns (relative_weight, mdc, drg_type, *_los) are populated
-- only for the systems that publish them (MS-DRG today) and are null elsewhere.
-- Not snapshot-grained: a full-refresh table read unscoped (plain ref).
with ms_drg as (
    select
        canonical_code_system,
        match_code,
        code_edition,
        code_description,
        effective_start,
        effective_end,
        code_description_source,
        code_description_license,
        source_url,
        retrieved_at,
        relative_weight,
        mdc,
        drg_type,
        geometric_mean_los,
        arithmetic_mean_los
    from {{ ref('stg_reference__ms_drg') }}
)

-- Future green-light systems union below this line with matching columns.
select * from ms_drg
