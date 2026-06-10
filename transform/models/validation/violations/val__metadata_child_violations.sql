with violations as (
    select
        n.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce({{ hpt_schema_family_from_version('hs.schema_version') }}, '3.0') as reported_schema_family,
        n.npi_ordinal,
        cast(null as integer) as provision_ordinal,
        'npi' as grain,
        'type_2_npi_ten_digit_numeric' as rule_id,
        'type_2_npi' as column_name,
        n.raw_npi as raw_value,
        'identifier_format_invalid' as diagnostic_type,
        'Type 2 NPI must be exactly ten digits.' as message
    from {{ hpt_scoped_ref('stg_bronze__type2_npi') }} n
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on n.snapshot_id = hs.snapshot_id
    where n.clean_npi is null or not regexp_matches(n.clean_npi, '^[0-9]{10}$')

    union all

    select
        g.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce({{ hpt_schema_family_from_version('hs.schema_version') }}, '3.0') as reported_schema_family,
        cast(null as integer) as npi_ordinal,
        g.provision_ordinal,
        'provision' as grain,
        'general_contract_provisions_required_shape' as rule_id,
        'general_contract_provisions.provisions' as column_name,
        g.raw_provisions as raw_value,
        'required_field_missing' as diagnostic_type,
        'General contract provisions object is present but provisions text is missing.' as message
    from {{ hpt_scoped_ref('stg_bronze__general_contract_provisions') }} g
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on g.snapshot_id = hs.snapshot_id
    where g.clean_provisions is null
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', 'v.rule_id', 'v.npi_ordinal', 'v.provision_ordinal',
            'v.raw_value'
        ]) }} as validation_violation_id,
        v.snapshot_id,
        v.hospital_id,
        v.source_format,
        v.source_format_family,
        v.reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        v.npi_ordinal,
        v.provision_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        cast(null as varchar) as structural_section,
        cast(null as integer) as record_ordinal,
        v.rule_id,
        r.rule_name,
        r.severity,
        v.grain,
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
