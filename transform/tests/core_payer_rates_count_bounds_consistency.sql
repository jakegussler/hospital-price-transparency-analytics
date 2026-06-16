{{ config(tags=['silver_core']) }}

-- Count bounds are a parsed interval over count_raw. They should either both
-- be null or form a valid inclusive range.
select
    silver_payer_rate_id,
    count_raw,
    count_min,
    count_max
from {{ hpt_scoped_ref('slv_core__payer_rates') }}
where
    (count_min is null) <> (count_max is null)
    or count_min > count_max
