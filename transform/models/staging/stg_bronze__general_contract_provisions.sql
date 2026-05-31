select
    snapshot_id,
    provision_ordinal,
    payer_name as raw_payer_name,
    {{ hpt_clean_text('payer_name') }} as clean_payer_name,
    plan_name as raw_plan_name,
    {{ hpt_clean_text('plan_name') }} as clean_plan_name,
    provisions as raw_provisions,
    {{ hpt_clean_text('provisions') }} as clean_provisions
from {{ source('bronze', 'general_contract_provisions') }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
