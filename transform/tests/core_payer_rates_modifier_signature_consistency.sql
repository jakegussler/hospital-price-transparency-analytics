-- Every rate whose standard charge carries modifiers in Silver Base must have a
-- non-zero modifier_count in Silver Core, every rate without modifiers must
-- carry the no-modifier sentinel signature, and count and signature must agree.
-- Modifiers live at standard-charge grain and fan out to every rate beneath.
with expected_modifier_rates as (
    select distinct payer_rates.silver_payer_rate_id
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }} charge_modifiers
    inner join {{ hpt_scoped_ref('slv_base__payer_rates') }} payer_rates
        on charge_modifiers.silver_standard_charge_id = payer_rates.silver_standard_charge_id
    where charge_modifiers.clean_modifier_code is not null
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
    or (core_rates.modifier_count = 0 and core_rates.modifier_signature <> {{ hpt_no_modifier_signature() }})
    or (core_rates.modifier_count > 0 and core_rates.modifier_signature = {{ hpt_no_modifier_signature() }})
