-- Every rate that carries modifiers in Silver Base (directly for CSV, via its
-- standard charge for JSON) must have a non-zero modifier_count in Silver
-- Core, every rate without modifiers must carry the no-modifier sentinel
-- signature, and count and signature must agree.
with expected_modifier_rates as (
    select distinct silver_payer_rate_id
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }}
    where silver_payer_rate_id is not null
        and clean_modifier_code is not null

    union

    select distinct payer_rates.silver_payer_rate_id
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }} charge_modifiers
    inner join {{ hpt_scoped_ref('slv_base__payer_rates') }} payer_rates
        on charge_modifiers.silver_standard_charge_id = payer_rates.silver_standard_charge_id
    where charge_modifiers.silver_payer_rate_id is null
        and charge_modifiers.clean_modifier_code is not null
),

core_rates as (
    select
        silver_payer_rate_id,
        modifier_signature,
        modifier_count
    from {{ hpt_scoped_ref('slv_core__payer_rates') }}
)

select
    core_rates.silver_payer_rate_id,
    core_rates.modifier_signature,
    core_rates.modifier_count,
    expected_modifier_rates.silver_payer_rate_id is not null as expected_modifiers
from core_rates
left join expected_modifier_rates
    on core_rates.silver_payer_rate_id = expected_modifier_rates.silver_payer_rate_id
where
    (expected_modifier_rates.silver_payer_rate_id is not null and core_rates.modifier_count = 0)
    or (expected_modifier_rates.silver_payer_rate_id is null and core_rates.modifier_count > 0)
    or (core_rates.modifier_count = 0 and core_rates.modifier_signature <> md5('<no_modifiers>'))
    or (core_rates.modifier_count > 0 and core_rates.modifier_signature = md5('<no_modifiers>'))
