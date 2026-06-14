{{ config(materialized='ephemeral') }}

-- CSV modifiers attach directly to a payer rate; JSON modifiers attach to a
-- standard charge and apply to every rate beneath it.
with rate_modifiers as (
    select
        silver_payer_rate_id,
        clean_modifier_code
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }}
    where silver_payer_rate_id is not null
        and clean_modifier_code is not null

    union all

    select
        payer_rates.silver_payer_rate_id,
        charge_modifiers.clean_modifier_code
    from {{ hpt_scoped_ref('slv_base__charge_modifiers') }} charge_modifiers
    inner join {{ hpt_scoped_ref('slv_base__payer_rates') }} payer_rates
        on charge_modifiers.silver_standard_charge_id = payer_rates.silver_standard_charge_id
    where charge_modifiers.silver_payer_rate_id is null
        and charge_modifiers.clean_modifier_code is not null
)

select
    silver_payer_rate_id,
    md5(
        string_agg(
            distinct upper(clean_modifier_code),
            '|' order by upper(clean_modifier_code)
        )
    ) as modifier_signature,
    count(distinct upper(clean_modifier_code)) as modifier_count
from rate_modifiers
group by silver_payer_rate_id
