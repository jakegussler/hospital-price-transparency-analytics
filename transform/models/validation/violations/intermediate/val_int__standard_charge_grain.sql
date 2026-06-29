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

csv_charge_grain as (
    -- CSV-wide Bronze is at charge x payer grain (row_ordinal repeats once per
    -- payer copy). The standard-charge-level fields are identical across those
    -- copies, and the payer-presence flags are an aggregate OVER them, so
    -- collapse to one row per (snapshot, row_ordinal) here. This both removes
    -- the per-payer fanout (the old r x b join keyed on row_ordinal alone was a
    -- payer x payer Cartesian product) and makes has_payer_* mean "any payer
    -- copy supplies a value" -- matching json_payer_rollup. See docs/cleanup.md.
    select
        snapshot_id,
        cast(row_ordinal as integer) as row_ordinal,
        any_value(standard_charge_gross) as raw_gross_charge,
        any_value(standard_charge_discounted_cash) as raw_discounted_cash,
        any_value(standard_charge_min) as raw_minimum,
        any_value(standard_charge_max) as raw_maximum,
        any_value(setting) as raw_setting,
        any_value(billing_class) as raw_billing_class,
        bool_or({{ hpt_clean_display_text('standard_charge_negotiated_dollar') }} is not null) as has_payer_dollar,
        bool_or({{ hpt_clean_display_text('standard_charge_negotiated_percentage') }} is not null) as has_payer_percentage,
        bool_or({{ hpt_clean_display_text('standard_charge_negotiated_algorithm') }} is not null) as has_payer_algorithm
    from {{ hpt_scoped_source('bronze', 'csv_charge_rows') }}
    group by snapshot_id, cast(row_ordinal as integer)
),

csv_charges as (
    select
        cg.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cg.row_ordinal,
        cg.raw_gross_charge,
        cg.raw_discounted_cash,
        cg.raw_minimum,
        cg.raw_maximum,
        cg.raw_setting,
        {{ hpt_clean_text('cg.raw_setting') }} as clean_setting,
        cg.raw_billing_class,
        {{ hpt_clean_text('cg.raw_billing_class') }} as clean_billing_class,
        cg.has_payer_dollar,
        cg.has_payer_percentage,
        cg.has_payer_algorithm
    from csv_charge_grain cg
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on cg.snapshot_id = hs.snapshot_id
)

select * from json_charges
union all
select * from csv_charges
