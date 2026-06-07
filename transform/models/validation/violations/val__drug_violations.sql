with json_drugs as (
    select
        d.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        sci.reported_schema_family,
        d.charge_item_id as source_charge_item_id,
        cast(null as integer) as row_ordinal,
        d.unit as raw_drug_unit,
        d.type as raw_drug_type,
        {{ hpt_clean_text('d.type') }} as clean_drug_type
    from {{ source('bronze', 'drug_information') }} d
    inner join {{ ref('stg_bronze__standard_charge_info') }} sci
        on d.snapshot_id = sci.snapshot_id
        and d.charge_item_id = sci.charge_item_id
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on d.snapshot_id = hs.snapshot_id
    where 1 = 1
        {{ hpt_snapshot_filter('d') }}
),

csv_drugs as (
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        r.row_ordinal,
        b.drug_unit_of_measurement as raw_drug_unit,
        b.drug_type_of_measurement as raw_drug_type,
        r.clean_drug_unit_type as clean_drug_type
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ source('bronze', 'csv_charge_rows') }} b
        on r.snapshot_id = b.snapshot_id
        and r.row_ordinal = cast(b.row_ordinal as integer)
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    where b.drug_unit_of_measurement is not null
        or b.drug_type_of_measurement is not null
),

drugs as (
    select * from json_drugs
    union all
    select * from csv_drugs
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
        'drug_information_required_shape_when_present' as rule_id,
        case when {{ hpt_clean_display_text('raw_drug_unit') }} is null then 'drug_information.unit' else 'drug_information.type' end as column_name,
        coalesce(raw_drug_unit, raw_drug_type) as raw_value,
        'required_field_missing' as diagnostic_type,
        'Drug information must include both unit and type when present.' as message
    from drugs
    where {{ hpt_clean_display_text('raw_drug_unit') }} is null
        or clean_drug_type is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'drug_unit_numeric_parseable', 'drug_information.unit', raw_drug_unit,
        'numeric_cast_failed',
        'Drug unit is non-empty but cannot be cast to double.'
    from drugs
    where reported_schema_family = '3.0'
        and {{ hpt_clean_display_text('raw_drug_unit') }} is not null
        and {{ hpt_safe_double('raw_drug_unit') }} is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'drug_unit_positive', 'drug_information.unit', raw_drug_unit,
        'numeric_not_positive',
        'Drug unit must be greater than zero.'
    from drugs
    where {{ hpt_safe_double('raw_drug_unit') }} is not null
        and {{ hpt_safe_double('raw_drug_unit') }} <= 0

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'drug_type_allowed_values', 'drug_information.type', raw_drug_type,
        'accepted_value_invalid',
        'Drug type is outside the CMS/NCPDP value set.'
    from drugs
    where clean_drug_type is not null
        and upper(clean_drug_type) not in ('GR', 'ME', 'ML', 'UN', 'F2', 'EA', 'GM')
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'drug'", 'v.rule_id', 'v.column_name',
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
        cast(null as integer) as npi_ordinal,
        cast(null as integer) as provision_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        cast(null as varchar) as structural_section,
        cast(null as integer) as record_ordinal,
        v.rule_id,
        r.rule_name,
        r.severity,
        'drug' as grain,
        r.disposition,
        v.column_name,
        v.raw_value,
        v.diagnostic_type,
        v.message,
        r.disposition = 'exclude_entity' as excludes_from_silver,
        r.cms_citation
    from violations v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
