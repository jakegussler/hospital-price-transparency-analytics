-- Code bridge for the rate-observation fact. Grain: one row per
-- (gold_rate_observation_id, silver_charge_item_code_id) = one amount observation
-- × each billing code on its charge item.
--
-- Built by joining gld_fct__rate_observations to slv_core__charge_item_codes on
-- (silver_charge_item_id, snapshot_id). An observation whose item carries no codes
-- produces NO bridge row (detected downstream via a left join / has_any_code on
-- the coverage scorecard). keeping it out of the fact is what lets gld_fct__rate_observations
-- stay additive and double-count-proof.
--
-- The bridge does NOT filter to comparable/specific codes: it EXPOSES the
-- comparability flags so the coverage scorecard can count non-comparable codes and
-- the comparison mart can apply the gate. service_code_key is populated only for
-- cross-hospital-comparable codes with a non-null match_code (exactly the
-- gld_dim__service_code membership) and is null otherwise, so the foreign key to
-- the conformed cohort dimension stays valid.
--
-- Snapshot-grained incremental (snapshot_replace on snapshot_id), same as the
-- fact; reads both inputs through hpt_scoped_ref so a scoped --snapshot-ids run
-- prunes Bronze partitions and bounds memory. Registered in
-- hpt_snapshot_grained_incremental_models().

with observations as (
    select
        gold_rate_observation_id,
        snapshot_id,
        hospital_id,
        silver_charge_item_id
    from {{ hpt_scoped_ref('gld_fct__rate_observations') }}
),

codes as (
    select
        silver_charge_item_code_id,
        silver_charge_item_id,
        snapshot_id,
        canonical_code_system,
        match_code,
        code_is_specific,
        code_cross_hospital_comparable,
        code_format_status,
        ndc_format_status
    from {{ hpt_scoped_ref('slv_core__charge_item_codes') }}
)

select
    obs.gold_rate_observation_id,
    codes.silver_charge_item_code_id,
    case
        when codes.code_cross_hospital_comparable = true
            and codes.match_code is not null
        then {{ hpt_surrogate_key(['codes.canonical_code_system', 'codes.match_code']) }}
    end as service_code_key,
    obs.snapshot_id,
    obs.hospital_id,
    codes.canonical_code_system,
    codes.match_code,
    codes.code_is_specific,
    codes.code_cross_hospital_comparable,
    codes.code_format_status,
    codes.ndc_format_status
from observations as obs
inner join codes
    on obs.silver_charge_item_id = codes.silver_charge_item_id
    and obs.snapshot_id = codes.snapshot_id
