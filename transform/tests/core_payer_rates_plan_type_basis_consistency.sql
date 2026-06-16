-- Invariants tying plan_type to plan_type_basis on the assembled payer-rate
-- fact. Returns offending rows when:
--   * basis 'none' does not coincide with a null plan_type (and vice versa), or
--   * a 'derived_plan_type' row's plan_type does not equal the deterministic
--     derivation of its clean_plan_name (i.e. the basis label and the value
--     disagree about provenance).
-- A payer_context_rule row may legitimately carry a plan_type the derivation
-- would not produce (the rule is authoritative), so it is not checked here.
select
    silver_payer_rate_id,
    clean_plan_name,
    plan_type,
    plan_type_basis
from {{ ref('slv_core__payer_rates') }}
where
    (plan_type_basis = 'none') <> (plan_type is null)
    or (
        plan_type_basis = 'derived_plan_type'
        and plan_type is distinct from ({{ hpt_derive_plan_type('clean_plan_name') }})
    )
