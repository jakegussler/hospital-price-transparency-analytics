select
    snapshot_id,
    charge_item_id,
    cast(code_ordinal as integer) as code_ordinal,
    code as raw_code,
    {{ hpt_trimmed_text('code') }} as clean_code,
    type as raw_code_type,
    {{ hpt_normalize_text('type') }} as clean_code_type
from {{ source('bronze', 'code_information') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
