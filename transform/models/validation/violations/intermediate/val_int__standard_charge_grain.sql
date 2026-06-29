-- One row per JSON standard charge and per CSV charge row, projected down to
-- only the fields the standard-charge validation rules evaluate. Materialized
-- as a table so val__standard_charge_violations scans it once per rule instead
-- of recomputing this JSON+CSV union (the per-rule re-scan was the dominant
-- temp-spill driver at full-corpus scale). See docs/cleanup.md.
with json_payer_rollup as (
    -- Parent standard-charge rules need to know whether any child payer rate
    -- supplies a negotiated value.
    select
        pi.snapshot_id,
        pi.standard_charge_id,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_dollar') }} is not null) as has_payer_dollar,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_percentage') }} is not null) as has_payer_percentage,
        bool_or({{ hpt_clean_display_text('pi.standard_charge_algorithm') }} is not null) as has_payer_algorithm
    from {{ hpt_scoped_source('bronze', 'payers_information') }} pi
    group by pi.snapshot_id, pi.standard_charge_id
),

json_charges as (
    select
        sc.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        sci.charge_item_id as source_charge_item_id,
        sc.standard_charge_id as source_standard_charge_id,
        cast(null as integer) as row_ordinal,
        sc.gross_charge as raw_gross_charge,
        sc.discounted_cash as raw_discounted_cash,
        sc.minimum as raw_minimum,
        sc.maximum as raw_maximum,
        sc.setting as raw_setting,
        {{ hpt_clean_text('sc.setting') }} as clean_setting,
        sc.billing_class as raw_billing_class,
        {{ hpt_clean_text('sc.billing_class') }} as clean_billing_class,
        coalesce(pr.has_payer_dollar, false) as has_payer_dollar,
        coalesce(pr.has_payer_percentage, false) as has_payer_percentage,
        coalesce(pr.has_payer_algorithm, false) as has_payer_algorithm
    from {{ hpt_scoped_source('bronze', 'standard_charges') }} sc
    inner join {{ hpt_scoped_ref('stg_bronze__standard_charge_info') }} sci
        on sc.snapshot_id = sci.snapshot_id
        and sc.charge_item_id = sci.charge_item_id
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on sc.snapshot_id = hs.snapshot_id
    left join json_payer_rollup pr
        on sc.snapshot_id = pr.snapshot_id
        and sc.standard_charge_id = pr.standard_charge_id
),

csv_charges as (
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        r.row_ordinal,
        b.standard_charge_gross as raw_gross_charge,
        b.standard_charge_discounted_cash as raw_discounted_cash,
        b.standard_charge_min as raw_minimum,
        b.standard_charge_max as raw_maximum,
        b.setting as raw_setting,
        r.clean_setting,
        b.billing_class as raw_billing_class,
        r.clean_billing_class,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_dollar') }} is not null as has_payer_dollar,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_percentage') }} is not null as has_payer_percentage,
        {{ hpt_clean_display_text('b.standard_charge_negotiated_algorithm') }} is not null as has_payer_algorithm
    from {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ hpt_scoped_source('bronze', 'csv_charge_rows') }} b
        on r.snapshot_id = b.snapshot_id
        and r.row_ordinal = cast(b.row_ordinal as integer)
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
)

select * from json_charges
union all
select * from csv_charges
