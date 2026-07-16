-- Reconciliation (decision 0021): every summary denominator must reconcile to
-- the representative layer it claims to describe, and the three-way hospital
-- denominator must be internally consistent. Each count supports a different
-- public claim, so drift in any of them misleads.
with hsa as (
    select
        service_context_key,
        count(*) as reporting_hospital_count,
        count(hospital_amount) as hospital_count,
        sum(raw_observation_count) as observation_count,
        sum(source_contract_count) as contract_count
    from {{ ref('gld_int__hospital_service_amounts') }}
    group by 1
)

select
    s.service_context_key
from {{ ref('gld_mart__service_price_summary') }} as s
join hsa
    on s.service_context_key = hsa.service_context_key
where s.reporting_hospital_count <> hsa.reporting_hospital_count
    or s.hospital_count <> hsa.hospital_count
    or s.excluded_hospital_count
        <> s.reporting_hospital_count - s.hospital_count
    or s.observation_count <> hsa.observation_count
    or s.contract_count is distinct from hsa.contract_count

union all

-- Contract counts reconcile to the contract-representative layer.
select
    s.service_context_key
from {{ ref('gld_mart__service_price_summary') }} as s
join (
    select service_context_key, count(*) as contract_count
    from {{ ref('gld_int__service_contract_representatives') }}
    group by 1
) as cr
    on s.service_context_key = cr.service_context_key
where s.contract_count is distinct from cr.contract_count
