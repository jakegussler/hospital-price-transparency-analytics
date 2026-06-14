-- Over-merge guard for the specific-code identity path: within one snapshot,
-- a single service_item_id should only absorb token-equal description
-- variants. Profiling at implementation time put the corpus-wide maximum at
-- 6 (word-order variants of one HCPCS item), so a spread above 10 indicates
-- a signature regression, not normal drift tolerance.
select
    service_item_id,
    snapshot_id,
    count(distinct clean_description) as distinct_description_count
from {{ hpt_scoped_ref('slv_core__charge_items') }}
where service_item_identity_basis = 'specific_code'
group by service_item_id, snapshot_id
having count(distinct clean_description) > 10
