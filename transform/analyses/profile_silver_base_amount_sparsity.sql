select
    source_format,
    rate_record_type,
    count(*) as rate_rows,
    count(gross_charge) as gross_charge_rows,
    count(discounted_cash) as discounted_cash_rows,
    count(minimum) as minimum_rows,
    count(maximum) as maximum_rows,
    count(negotiated_dollar) as negotiated_dollar_rows,
    count(negotiated_percentage) as negotiated_percentage_rows,
    count(negotiated_algorithm) as negotiated_algorithm_rows,
    count(median_amount) as median_amount_rows
from {{ ref('slv_base__payer_rates') }}
group by source_format, rate_record_type
order by source_format, rate_record_type
