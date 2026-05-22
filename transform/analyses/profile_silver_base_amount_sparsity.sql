select
    'standard_charges' as model_name,
    source_format,
    count(*) as rows,
    count(gross_charge) as gross_charge_rows,
    count(discounted_cash) as discounted_cash_rows,
    count(minimum) as minimum_rows,
    count(maximum) as maximum_rows,
    cast(null as bigint) as negotiated_dollar_rows,
    cast(null as bigint) as negotiated_percentage_rows,
    cast(null as bigint) as negotiated_algorithm_rows,
    cast(null as bigint) as median_amount_rows
from {{ ref('slv_base__standard_charges') }}
group by source_format

union all

select
    'payer_rates' as model_name,
    source_format,
    count(*) as rows,
    cast(null as bigint) as gross_charge_rows,
    cast(null as bigint) as discounted_cash_rows,
    cast(null as bigint) as minimum_rows,
    cast(null as bigint) as maximum_rows,
    count(negotiated_dollar) as negotiated_dollar_rows,
    count(negotiated_percentage) as negotiated_percentage_rows,
    count(negotiated_algorithm) as negotiated_algorithm_rows,
    count(median_amount) as median_amount_rows
from {{ ref('slv_base__payer_rates') }}
group by source_format
order by model_name, source_format
