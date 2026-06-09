select
    modifier_code_id,
    snapshot_id,
    code as raw_modifier_code,
    {{ hpt_trimmed_text('code') }} as clean_modifier_code,
    description as raw_description,
    {{ hpt_normalize_text('description') }} as clean_description,
    setting as raw_setting,
    {{ hpt_normalize_text('setting') }} as clean_setting
from {{ source('bronze', 'modifiers') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
