{{ config(materialized='ephemeral') }}

-- Modifiers attach to a standard charge (uniform grain in
-- slv_base__charge_modifiers) and apply to every payer rate beneath it. This is
-- the single point where that standard-charge -> payer-rate fan-out happens.
with rate_modifiers as (
    select
        payer_rates.silver_payer_rate_id,
        charge_modifiers.clean_modifier_code
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }} charge_modifiers
    inner join {{ hpt_scoped_ref('slv_base__payer_rates') }} payer_rates
        on charge_modifiers.silver_standard_charge_id = payer_rates.silver_standard_charge_id
    where charge_modifiers.clean_modifier_code is not null
)

select
    silver_payer_rate_id,
    {{ hpt_modifier_signature('upper(clean_modifier_code)') }} as modifier_signature,
    count(distinct upper(clean_modifier_code)) as modifier_count
from rate_modifiers
group by silver_payer_rate_id
