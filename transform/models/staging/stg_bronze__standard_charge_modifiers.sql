select
    snapshot_id,
    standard_charge_id,
    modifier_code as raw_modifier_code,
    {{ hpt_clean_display_text('modifier_code') }} as clean_modifier_code,
    cast(modifier_ordinal as integer) as modifier_ordinal
from {{ source('bronze', 'standard_charge_modifiers') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
