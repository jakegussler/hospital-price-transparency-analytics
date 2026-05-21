with csv_codes as (
    {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
),

csv_code_sets as (
    select
        snapshot_id,
        row_ordinal,
        md5(
            coalesce(
                string_agg(
                    coalesce({{ hpt_clean_display_text('raw_code') }}, '') || ':' || coalesce({{ hpt_clean_text('raw_code_type') }}, ''),
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
        r.*,
        coalesce(cs.code_set_signature, md5('<no_codes>')) as code_set_signature
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    left join csv_code_sets cs
        on r.snapshot_id = cs.snapshot_id
        and r.row_ordinal = cs.row_ordinal
),

signed_rows as (
    select
        *,
        {{ hpt_surrogate_key([
            'snapshot_id',
            'clean_description',
            'code_set_signature',
            'clean_setting',
            'clean_billing_class',
            'drug_unit',
            'clean_drug_unit_type'
        ]) }} as charge_item_signature
    from csv_rows
)

select
    {{ hpt_surrogate_key(['snapshot_id', "'csv'", 'charge_item_signature']) }} as silver_charge_item_id,
    charge_item_signature,
    snapshot_id,
    row_ordinal,
    source_format,
    raw_description,
    clean_description,
    code_set_signature,
    raw_setting,
    clean_setting,
    raw_billing_class,
    clean_billing_class,
    drug_unit,
    raw_drug_unit_type,
    clean_drug_unit_type
from signed_rows
