{% if hpt_has_bronze_files('standard_charge_modifiers') %}
    select
        snapshot_id,
        standard_charge_id,
        modifier_code as raw_modifier_code,
        {{ hpt_clean_display_text('modifier_code') }} as clean_modifier_code,
        cast(modifier_ordinal as integer) as modifier_ordinal
    from {{ source('bronze', 'standard_charge_modifiers') }}
{% else %}
    select
        cast(null as varchar) as snapshot_id,
        cast(null as varchar) as standard_charge_id,
        cast(null as varchar) as raw_modifier_code,
        cast(null as varchar) as clean_modifier_code,
        cast(null as integer) as modifier_ordinal
    where false
{% endif %}
