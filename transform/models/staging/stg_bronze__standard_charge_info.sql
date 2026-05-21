select
    charge_item_id,
    snapshot_id,
    description as raw_description,
    {{ hpt_clean_text('description') }} as clean_description,
    cast(item_ordinal as integer) as item_ordinal
from {{ source('bronze', 'standard_charge_info') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
