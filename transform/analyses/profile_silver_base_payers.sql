select
    clean_payer_name,
    count(*) as payer_rate_rows,
    count(distinct raw_payer_name) as raw_payer_name_variants,
    count(distinct hospital_id) as hospitals,
    count(distinct snapshot_id) as snapshots,
    string_agg(distinct raw_payer_name, ' | ' order by raw_payer_name) as raw_payer_examples
from {{ ref('slv_base__payer_rates') }}
where clean_payer_name is not null
group by clean_payer_name
order by payer_rate_rows desc
limit 100
