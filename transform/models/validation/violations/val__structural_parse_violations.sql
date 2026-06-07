with diagnostics as (
    select
        d.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce(
            d.reported_schema_family,
            d.parser_schema_family,
            {{ hpt_schema_family_from_version('hs.schema_version') }}
        ) as reported_schema_family,
        d.record_ordinal,
        d.section,
        d.error_summary
    from {{ ref('stg_bronze__json_record_parse_diagnostics') }} d
    left join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on d.snapshot_id = hs.snapshot_id
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'd.snapshot_id', "'structural'", "'json_record_structural_parse_failed'",
            'd.section', 'd.record_ordinal', 'd.error_summary'
        ]) }} as validation_violation_id,
        d.snapshot_id,
        d.hospital_id,
        d.source_format,
        d.source_format_family,
        d.reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        cast(null as integer) as npi_ordinal,
        cast(null as integer) as provision_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        d.section as structural_section,
        d.record_ordinal,
        r.rule_id,
        r.rule_name,
        r.severity,
        'structural' as grain,
        r.disposition,
        d.section as column_name,
        d.error_summary as raw_value,
        'json_structural_parse_failed' as diagnostic_type,
        'JSON record was quarantined before Bronze row construction; see parser diagnostic summary.' as message,
        false as excludes_from_silver,
        r.cms_citation
    from diagnostics d
    inner join {{ ref('cms_validation_rules') }} r
        on r.rule_id = 'json_record_structural_parse_failed'
)

select * from enriched
