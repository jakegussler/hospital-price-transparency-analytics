-- One row per code (JSON code_information object and CSV code_N/code_N_type
-- pair), joined to the code-type seed for membership/applicability checks.
-- Materialized as a table so val__code_violations scans it once per rule
-- instead of recomputing this JSON+CSV union for every code rule branch.
-- See docs/cleanup.md.
with json_codes as (
    select
        c.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        c.charge_item_id as source_charge_item_id,
        cast(null as integer) as row_ordinal,
        c.code_ordinal,
        c.raw_code,
        c.clean_code,
        c.raw_code_type,
        c.clean_code_type
    from {{ hpt_scoped_ref('stg_bronze__code_information') }} c
    inner join {{ hpt_scoped_ref('stg_bronze__standard_charge_info') }} sci
        on c.snapshot_id = sci.snapshot_id
        and c.charge_item_id = sci.charge_item_id
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on c.snapshot_id = hs.snapshot_id
),

csv_code_rows as (
    select
        p.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        p.row_ordinal,
        p.code_ordinal,
        p.raw_code,
        {{ hpt_clean_display_text('p.raw_code') }} as clean_code,
        p.raw_code_type,
        {{ hpt_clean_text('p.raw_code_type') }} as clean_code_type
    from {{ hpt_scoped_ref('val_int__csv_code_pairs') }} p
    inner join {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
        on p.snapshot_id = r.snapshot_id
        and p.row_ordinal = r.row_ordinal
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on p.snapshot_id = hs.snapshot_id
),

code_rows as (
    select * from json_codes
    union all
    select * from csv_code_rows
)

-- The code-type seed supports both global membership and exact schema-family
-- applicability checks.
select
    cr.*,
    ct.code_type as matched_code_type,
    ct.valid_in_2_1,
    ct.valid_in_2_2,
    ct.valid_in_3_0
from code_rows cr
left join {{ ref('cms_code_types') }} ct
    on cr.clean_code_type = ct.code_type
