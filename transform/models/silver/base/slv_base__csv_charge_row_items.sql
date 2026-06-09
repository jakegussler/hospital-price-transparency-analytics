with rejected_csv_codes as (
    select distinct snapshot_id, row_ordinal, code_ordinal
    from {{ ref('val__code_rejections') }}
    where source_format_family = 'csv'
),

rejected_csv_drugs as (
    select distinct snapshot_id, row_ordinal
    from {{ ref('val__drug_rejections') }}
    where source_format_family = 'csv'
),

csv_codes as (
    select codes.*
    from (
        {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
    ) codes
    left join rejected_csv_codes r
        on r.snapshot_id = codes.snapshot_id
        and r.row_ordinal = codes.row_ordinal
        and r.code_ordinal = codes.code_ordinal
    where r.snapshot_id is null
),

csv_code_sets as (
    select
        snapshot_id,
        row_ordinal,
        md5(
            coalesce(
                string_agg(
                    coalesce({{ hpt_trimmed_text('raw_code') }}, '') || ':' || coalesce({{ hpt_normalize_text('raw_code_type') }}, ''),
                    '|' order by code_ordinal, raw_code, raw_code_type
                ),
                '<no_codes>'
            )
        ) as code_set_signature
    from csv_codes
    group by snapshot_id, row_ordinal
),

csv_rows as (
    select
        r.* exclude (drug_unit, raw_drug_unit_type, clean_drug_unit_type),
        case when dr.snapshot_id is null then r.drug_unit end as drug_unit,
        case when dr.snapshot_id is null then r.raw_drug_unit_type end as raw_drug_unit_type,
        case when dr.snapshot_id is null then r.clean_drug_unit_type end as clean_drug_unit_type,
        coalesce(cs.code_set_signature, md5('<no_codes>')) as code_set_signature
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on r.snapshot_id = mr.snapshot_id
        and r.row_ordinal = mr.row_ordinal
        and not mr.is_standalone_modifier
    left join csv_code_sets cs
        on r.snapshot_id = cs.snapshot_id
        and r.row_ordinal = cs.row_ordinal
    left join rejected_csv_drugs dr
        on r.snapshot_id = dr.snapshot_id
        and r.row_ordinal = dr.row_ordinal
),

signed_rows as (
    select
        *,
        {{ hpt_surrogate_key([
            'snapshot_id',
            'clean_description',
            'code_set_signature',
            'drug_unit',
            'clean_drug_unit_type'
        ]) }} as charge_item_signature
    from csv_rows
)

select distinct
    {{ hpt_surrogate_key(['snapshot_id', "'csv'", 'charge_item_signature']) }} as silver_charge_item_id,
    charge_item_signature,
    snapshot_id,
    row_ordinal,
    source_format,
    raw_description,
    clean_description,
    code_set_signature,
    drug_unit,
    raw_drug_unit_type,
    clean_drug_unit_type
from signed_rows
where not exists (
    select 1
    from {{ ref('val__charge_item_rejections') }} r
    where r.source_format_family = 'csv'
        and r.snapshot_id = signed_rows.snapshot_id
        and r.row_ordinal = signed_rows.row_ordinal
)
