with record_counts as (
    select snapshot_id, 'header' as grain, count(*) as total_records
    from {{ ref('stg_bronze__hospital_mrf_snapshots') }}
    group by snapshot_id
    union all
    select snapshot_id, 'charge_item', count(*)
    from {{ ref('stg_bronze__standard_charge_info') }}
    group by snapshot_id
    union all
    select snapshot_id, 'standard_charge', count(*)
    from {{ ref('stg_bronze__standard_charges') }}
    group by snapshot_id
    union all
    select snapshot_id, 'payer_rate', count(*)
    from {{ ref('stg_bronze__payers_information') }}
    group by snapshot_id
    union all
    select snapshot_id, 'code', count(*)
    from {{ ref('stg_bronze__code_information') }}
    group by snapshot_id
    union all
    select snapshot_id, 'drug', count(*)
    from {{ ref('stg_bronze__drug_information') }}
    group by snapshot_id
    union all
    select snapshot_id, 'modifier', count(*)
    from {{ ref('stg_bronze__modifiers') }}
    group by snapshot_id
    union all
    select snapshot_id, 'modifier_payer', count(*)
    from {{ ref('stg_bronze__modifier_payer_info') }}
    group by snapshot_id
    union all
    select snapshot_id, 'npi', count(*)
    from {{ ref('stg_bronze__type2_npi') }}
    group by snapshot_id
    union all
    select snapshot_id, 'provision', count(*)
    from {{ ref('stg_bronze__general_contract_provisions') }}
    group by snapshot_id
    union all
    select snapshot_id, 'structural', count(*)
    from {{ ref('stg_bronze__json_record_parse_diagnostics') }}
    group by snapshot_id
    union all
    select snapshot_id, 'charge_item', count(distinct row_ordinal)
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id
    union all
    select snapshot_id, 'standard_charge', count(distinct row_ordinal)
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id
    union all
    select snapshot_id, 'payer_rate', count(*)
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id
),

record_totals as (
    select snapshot_id, grain, sum(total_records) as total_records
    from record_counts
    group by snapshot_id, grain
),

violations as (
    select
        snapshot_id,
        hospital_id,
        source_format,
        grain,
        rule_id,
        severity,
        count(*) as violation_count,
        count(*) filter (where is_rejected) as rejected_violation_count
    from {{ ref('val__all_violations') }}
    group by
        snapshot_id,
        hospital_id,
        source_format,
        grain,
        rule_id,
        severity
)

select
    v.snapshot_id,
    v.hospital_id,
    v.source_format,
    v.grain,
    v.rule_id,
    v.severity,
    coalesce(rt.total_records, 0) as total_records,
    v.violation_count,
    v.rejected_violation_count,
    case
        when coalesce(rt.total_records, 0) = 0 then null
        else greatest(0.0, 1.0 - (v.violation_count::double / rt.total_records::double))
    end as pass_rate
from violations v
left join record_totals rt
    on v.snapshot_id = rt.snapshot_id
    and v.grain = rt.grain
