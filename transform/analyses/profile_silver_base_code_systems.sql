select
    source_format,
    clean_code_type,
    canonical_code_system,
    count(*) as code_rows,
    count(distinct hospital_id) as hospitals,
    count(distinct snapshot_id) as snapshots
from {{ ref('slv_base__charge_item_codes') }}
group by source_format, clean_code_type, canonical_code_system
order by code_rows desc
