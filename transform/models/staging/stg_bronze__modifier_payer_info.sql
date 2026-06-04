select
    snapshot_id,
    modifier_code_id,
    payer_name as raw_payer_name,
    {{ hpt_clean_text('payer_name') }} as clean_payer_name,
    plan_name as raw_plan_name,
    {{ hpt_clean_text('plan_name') }} as clean_plan_name,
    description as raw_description,
    {{ hpt_clean_text('description') }} as clean_description
from {{ source('bronze', 'modifier_payer_info') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
