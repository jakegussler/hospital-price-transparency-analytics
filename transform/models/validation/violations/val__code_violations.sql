-- Normalize JSON code objects and unpivoted CSV code pairs to one code grain,
-- then emit code-level and missing-CSV-code violations.
with csv_codes as (
    {{ hpt_csv_code_unpivot("select * from " ~ ref('stg_bronze__csv_charge_rows')) }}
),

code_types as (
    select * from {{ ref('cms_code_types') }}
),

json_codes as (
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
    from {{ ref('stg_bronze__code_information') }} c
    inner join {{ ref('stg_bronze__standard_charge_info') }} sci
        on c.snapshot_id = sci.snapshot_id
        and c.charge_item_id = sci.charge_item_id
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on c.snapshot_id = hs.snapshot_id
),

csv_code_rows as (
    select
        c.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        c.row_ordinal,
        c.code_ordinal,
        c.raw_code,
        {{ hpt_clean_display_text('c.raw_code') }} as clean_code,
        c.raw_code_type,
        {{ hpt_clean_text('c.raw_code_type') }} as clean_code_type
    from csv_codes c
    inner join {{ ref('stg_bronze__csv_charge_rows') }} r
        on c.snapshot_id = r.snapshot_id
        and c.row_ordinal = r.row_ordinal
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on c.snapshot_id = hs.snapshot_id
),

code_rows as (
    select * from json_codes
    union all
    select * from csv_code_rows
),

code_rows_with_type_metadata as (
    -- The code-type seed supports both global membership and exact
    -- schema-family applicability checks.
    select
        cr.*,
        ct.code_type as matched_code_type,
        ct.valid_in_2_1,
        ct.valid_in_2_2,
        ct.valid_in_3_0
    from code_rows cr
    left join code_types ct
        on cr.clean_code_type = ct.code_type
),

csv_rows_without_codes as (
    -- Rows with charge data but no code pair cannot appear in the code-grain
    -- union, so retain them separately for the CSV conditional rule.
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        r.row_ordinal
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on r.snapshot_id = mr.snapshot_id
        and r.row_ordinal = mr.row_ordinal
        and not mr.is_standalone_modifier
    left join csv_codes c
        on r.snapshot_id = c.snapshot_id
        and r.row_ordinal = c.row_ordinal
    where c.row_ordinal is null
        and (
            r.gross_charge is not null
            or r.discounted_cash is not null
            or r.negotiated_dollar is not null
            or r.negotiated_percentage is not null
            or r.negotiated_algorithm is not null
        )
),

violations as (
    -- Required shape, accepted-value, and non-empty text rules.
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
        code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'code_information_required_shape' as rule_id,
        case when clean_code is null then 'code' else 'type' end as column_name,
        coalesce(raw_code, raw_code_type) as raw_value,
        'code_pair_incomplete' as diagnostic_type,
        'Code and code type must be present as a pair.' as message
    from code_rows
    where clean_code is null or clean_code_type is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        code_ordinal, cast(null as varchar),
        'code_type_allowed_values', 'code_type', raw_code_type,
        'accepted_value_invalid',
        'Code type is not in the project-wide CMS code type value set.'
    from code_rows_with_type_metadata
    where clean_code_type is not null
        and matched_code_type is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        code_ordinal, cast(null as varchar),
        'code_type_family_specific_enum', 'code_type', raw_code_type,
        'family_accepted_value_invalid',
        'Code type is valid globally but not for the reported schema family.'
    from code_rows_with_type_metadata
    where matched_code_type is not null
        and (
            (reported_schema_family = '2.1' and not valid_in_2_1)
            or (reported_schema_family = '2.2' and not valid_in_2_2)
            or (reported_schema_family = '3.0' and not valid_in_3_0)
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        code_ordinal, cast(null as varchar),
        'code_text_non_empty',
        case when raw_code is not null and trim(cast(raw_code as varchar)) = '' then 'code' else 'type' end,
        case when raw_code is not null and trim(cast(raw_code as varchar)) = '' then raw_code else raw_code_type end,
        'required_text_blank',
        'Required code fields must not be blank.'
    from code_rows
    where (raw_code is not null and trim(cast(raw_code as varchar)) = '')
        or (raw_code_type is not null and trim(cast(raw_code_type as varchar)) = '')

    union all

    -- CSV charge rows that are missing every code/code-type pair.
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), row_ordinal, cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'csv_code_pair_required', 'code|[i]', null,
        'csv_code_pair_missing',
        'CSV charge row has charge data but no code/code-type pair.'
    from csv_rows_without_codes
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'code'", 'v.rule_id', 'v.column_name',
            'v.source_charge_item_id', 'v.row_ordinal', 'v.code_ordinal',
            'v.raw_value'
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
        'code' as grain,
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
