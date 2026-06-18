-- Guard: a within-hospital service_item_id must never span hospitals.
--
-- Decision 0014 fixes cross-hospital comparison as a Gold code-cohort join,
-- never a shared item master, and hashes hospital_id into every identity basis
-- to enforce it. A service_item_id mapping to more than one hospital_id would
-- mean hospital_id was dropped from the key (a logic regression) or, vanishingly,
-- an md5 collision. Either way Gold's cross-hospital boundary would be broken,
-- so this fails the build. Reads the minting site (slv_core__charge_items)
-- unscoped so it holds across the whole retained corpus, not just one snapshot.
select
    service_item_id,
    count(distinct hospital_id) as hospital_count
from {{ ref('slv_core__charge_items') }}
group by service_item_id
having count(distinct hospital_id) > 1
