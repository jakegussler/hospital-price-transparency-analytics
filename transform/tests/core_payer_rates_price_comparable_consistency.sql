{{ config(tags=['silver_core']) }}

-- is_price_comparable is a convenience gate and must never drift from the
-- tier that defines it.
select
    silver_payer_rate_id,
    amount_comparability_tier,
    is_price_comparable
from {{ hpt_scoped_ref('slv_core__payer_rates') }}
where is_price_comparable is distinct from (
    amount_comparability_tier = 'comparable_dollar'
)
