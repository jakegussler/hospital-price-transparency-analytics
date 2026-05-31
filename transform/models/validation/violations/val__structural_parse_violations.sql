with diagnostics as (
    select
        d.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce(d.reported_schema_family, d.accepted_schema_family, {{ hpt_schema_family_from_version('hs.schema_version') }}) as reported_schema_family,
        d.record_ordinal,
        d.section,
        d.error_summary,
        d.final_status
    from {{ ref('stg_bronze__json_record_parse_diagnostics') }} d
    left join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on d.snapshot_id = hs.snapshot_id
    where d.final_status = 'quarantined'
),

structural_rules as (
    select rule_id
    from {{ ref('cms_validation_rules') }}
    where rule_id in (
        'standard_charge_information_required_shape',
        'code_information_required_shape',
        'drug_information_required_shape_when_present',
        'standard_charge_required_setting_shape',
        'modifier_information_required_shape',
        'required_arrays_non_empty'
    )
),

violations as (
    select
        d.snapshot_id,
        d.hospital_id,
        d.source_format,
        d.source_format_family,
        d.reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        d.record_ordinal as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        r.rule_id,
        d.section as column_name,
        d.error_summary as raw_value,
        'json_structural_parse_failed' as diagnostic_type,
        'JSON record was quarantined before Bronze row construction; see parser diagnostic summary.' as message
    from diagnostics d
    cross join structural_rules r
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'structural'", 'v.rule_id', 'v.column_name',
            'v.row_ordinal', 'v.raw_value'
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
