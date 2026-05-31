with code_types as (
    select * from {{ ref('cms_code_types') }}
),

json_items as (
    select
        sci.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        sci.charge_item_id as source_charge_item_id,
        cast(null as integer) as row_ordinal,
        sci.raw_description,
        sci.clean_description,
        di.drug_unit,
        di.clean_drug_unit_type
    from {{ ref('stg_bronze__standard_charge_info') }} sci
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on sci.snapshot_id = hs.snapshot_id
    left join {{ ref('stg_bronze__drug_information') }} di
        on sci.snapshot_id = di.snapshot_id
        and sci.charge_item_id = di.charge_item_id
),

json_item_rollup as (
    select
        i.*,
        count(c.code_ordinal) as code_count,
        count(sc.standard_charge_id) as standard_charge_count,
        bool_or(coalesce(ct.requires_drug_information, false)) as has_drug_information_code
    from json_items i
    left join {{ ref('stg_bronze__code_information') }} c
        on i.snapshot_id = c.snapshot_id
        and i.source_charge_item_id = c.charge_item_id
    left join code_types ct
        on c.clean_code_type = ct.code_type
    left join {{ ref('stg_bronze__standard_charges') }} sc
        on i.snapshot_id = sc.snapshot_id
        and i.source_charge_item_id = sc.charge_item_id
    group by all
),

csv_codes as (
    {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
),

csv_item_rollup as (
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        r.row_ordinal,
        r.raw_description,
        r.clean_description,
        r.drug_unit,
        r.clean_drug_unit_type,
        count(c.code_ordinal) as code_count,
        bool_or(coalesce(ct.requires_drug_information, false)) as has_drug_information_code
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    left join csv_codes c
        on r.snapshot_id = c.snapshot_id
        and r.row_ordinal = c.row_ordinal
    left join code_types ct
        on {{ hpt_clean_text('c.raw_code_type') }} = ct.code_type
    group by all
),

items as (
    select * from json_item_rollup
    union all
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        source_charge_item_id,
        row_ordinal,
        raw_description,
        clean_description,
        drug_unit,
        clean_drug_unit_type,
        code_count,
        cast(null as bigint) as standard_charge_count,
        has_drug_information_code
    from csv_item_rollup
),

violations as (
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'ndc_requires_drug_information' as rule_id,
        'drug_information' as column_name,
        concat('drug_unit=', coalesce(cast(drug_unit as varchar), '<null>'), '; drug_type=', coalesce(clean_drug_unit_type, '<null>')) as raw_value,
        'conditional_required_field_missing' as diagnostic_type,
        'NDC code rows require both drug unit and drug type for schema families 2.2 and 3.0.' as message
    from items
    where reported_schema_family in ('2.2', '3.0')
        and has_drug_information_code
        and (drug_unit is null or clean_drug_unit_type is null)

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'required_text_non_empty', 'description', raw_description,
        'required_text_blank',
        'Charge-item description is required and must not be blank.'
    from items
    where raw_description is not null and trim(cast(raw_description as varchar)) = ''

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'required_arrays_non_empty', 'code_information',
        cast(code_count as varchar), 'required_array_empty',
        'JSON code_information array must contain at least one item.'
    from items
    where source_format_family = 'json' and code_count = 0

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'required_arrays_non_empty', 'standard_charges',
        cast(standard_charge_count as varchar), 'required_array_empty',
        'JSON standard_charges array must contain at least one item.'
    from items
    where source_format_family = 'json' and standard_charge_count = 0
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'charge_item'", 'v.rule_id', 'v.column_name',
            'v.source_charge_item_id', 'v.row_ordinal', 'v.raw_value'
        ]) }} as validation_violation_id,
        v.snapshot_id,
        v.hospital_id,
        v.source_format,
        v.source_format_family,
        v.reported_schema_family,
        v.source_charge_item_id,
        v.source_standard_charge_id,
        v.payer_ordinal,
        v.row_ordinal,
        v.source_rate_ordinal,
        v.code_ordinal,
        v.modifier_code_id,
        v.rule_id,
        r.rule_name,
        r.severity,
        r.grain,
        v.column_name,
        v.raw_value,
        v.diagnostic_type,
        v.message,
        r.severity = 'reject' as is_rejected,
        r.cms_citation
    from violations v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
