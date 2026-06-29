-- Profiling: legible example services. Service + context groups that (a)
-- clear the 3-hospital denominator floor and (b) carry a human-readable
-- description from green-light reference data (MS-DRG today), with their
-- cross-hospital price spread. Lets the README show a few concrete, named price
-- examples instead of memorized codes. Ordered by breadth of reporting hospitals.
select
    scd.canonical_code_system,
    scd.match_code,
    scd.code_description,
    sps.clean_setting,
    sps.clean_billing_class,
    sps.amount_kind,
    sps.hospital_count,
    sps.observation_count,
    round(sps.median_amount, 2) as median_amount,
    round(sps.p10_amount, 2) as p10_amount,
    round(sps.p90_amount, 2) as p90_amount,
    round(sps.spread_ratio_p90_to_p10, 2) as spread_ratio_p90_to_p10
from {{ ref('gld_mart__service_price_summary') }} as sps
inner join {{ ref('gld_dim__service_code') }} as scd
    on sps.service_code_key = scd.service_code_key
where sps.meets_hospital_threshold
  and scd.has_code_description
order by sps.hospital_count desc, sps.observation_count desc, sps.spread_ratio_p90_to_p10 desc
limit 20
