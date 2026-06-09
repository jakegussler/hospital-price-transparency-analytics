-- clean_payer_name, clean_plan_name, and clean_methodology are nullified at
-- staging via hpt_nullify_sentinel_text, so placeholder values such as 'null',
-- 'n/a', or 'unknown' must never survive into the silver payer-rate grain. Any
-- surviving sentinel means a staging model dropped the nullify treatment or a
-- new sentinel token needs to be added to the macro.
with sentinels as (
    select unnest([
        'null',
        'none',
        'n/a',
        'na',
        'not applicable',
        'not available',
        'unknown',
        '-'
    ]) as sentinel
)

select
    pr.silver_payer_rate_id,
    'clean_payer_name' as column_name,
    pr.clean_payer_name as offending_value
from {{ ref('slv_base__payer_rates') }} pr
where pr.clean_payer_name in (select sentinel from sentinels)

union all

select
    pr.silver_payer_rate_id,
    'clean_plan_name' as column_name,
    pr.clean_plan_name as offending_value
from {{ ref('slv_base__payer_rates') }} pr
where pr.clean_plan_name in (select sentinel from sentinels)

union all

select
    pr.silver_payer_rate_id,
    'clean_methodology' as column_name,
    pr.clean_methodology as offending_value
from {{ ref('slv_base__payer_rates') }} pr
where pr.clean_methodology in (select sentinel from sentinels)
