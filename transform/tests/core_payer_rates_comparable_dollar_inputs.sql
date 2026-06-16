{{ config(tags=['silver_core']) }}

-- Comparable dollars must be actual negotiated dollars from methodologies
-- whose dollar field is a directly contracted price, not a derived amount.
select
    silver_payer_rate_id,
    methodology,
    negotiated_dollar,
    amount_kind,
    amount_comparability_tier
from {{ hpt_scoped_ref('slv_core__payer_rates') }}
where amount_comparability_tier = 'comparable_dollar'
    and (
        amount_kind <> 'dollar'
        or negotiated_dollar is null
        or methodology not in ('fee schedule', 'case rate', 'per diem')
    )
