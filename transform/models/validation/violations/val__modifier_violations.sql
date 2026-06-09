-- Validate JSON modifier definitions/children and CSV standalone modifier rules
-- while preserving their distinct parent and payer-child source keys.
with json_modifiers as (
    select
        m.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce({{ hpt_schema_family_from_version('hs.schema_version') }}, '3.0') as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        m.modifier_code_id,
        m.raw_modifier_code,
        m.clean_modifier_code,
        m.raw_description,
        m.clean_description,
        m.raw_setting,
        m.clean_setting,
        cast(null as varchar) as raw_payer_name,
        cast(null as varchar) as clean_payer_name,
        cast(null as varchar) as raw_plan_name,
        cast(null as varchar) as clean_plan_name,
        cast(null as varchar) as raw_payer_description,
        cast(null as varchar) as clean_payer_description,
        cast(null as decimal(18, 4)) as negotiated_dollar,
        cast(null as double) as negotiated_percentage,
        cast(null as varchar) as negotiated_algorithm,
        cast(null as varchar) as raw_methodology,
        cast(null as varchar) as clean_methodology,
        cast(null as decimal(18, 4)) as median_amount,
        cast(null as decimal(18, 4)) as tenth_percentile,
        cast(null as decimal(18, 4)) as ninetieth_percentile,
        cast(null as varchar) as raw_count,
        cast(null as varchar) as additional_generic_notes,
        cast(null as varchar) as additional_payer_notes
    from {{ ref('stg_bronze__modifiers') }} m
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on m.snapshot_id = hs.snapshot_id
),

json_modifier_payers as (
    select
        mpi.snapshot_id,
        hs.hospital_id,
        hs.source_format,
        {{ hpt_source_format_family('hs.source_format') }} as source_format_family,
        coalesce({{ hpt_schema_family_from_version('hs.schema_version') }}, '3.0') as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        mpi.modifier_payer_ordinal,
        mpi.modifier_code_id,
        cast(null as varchar) as raw_modifier_code,
        cast(null as varchar) as clean_modifier_code,
        cast(null as varchar) as raw_description,
        cast(null as varchar) as clean_description,
        cast(null as varchar) as raw_setting,
        cast(null as varchar) as clean_setting,
        mpi.raw_payer_name,
        mpi.clean_payer_name,
        mpi.raw_plan_name,
        mpi.clean_plan_name,
        mpi.raw_description as raw_payer_description,
        mpi.clean_description as clean_payer_description,
        cast(null as decimal(18, 4)) as negotiated_dollar,
        cast(null as double) as negotiated_percentage,
        cast(null as varchar) as negotiated_algorithm,
        cast(null as varchar) as raw_methodology,
        cast(null as varchar) as clean_methodology,
        cast(null as decimal(18, 4)) as median_amount,
        cast(null as decimal(18, 4)) as tenth_percentile,
        cast(null as decimal(18, 4)) as ninetieth_percentile,
        cast(null as varchar) as raw_count,
        cast(null as varchar) as additional_generic_notes,
        cast(null as varchar) as additional_payer_notes
    from {{ ref('stg_bronze__modifier_payer_info') }} mpi
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on mpi.snapshot_id = hs.snapshot_id
),

csv_modifier_rules as (
    select
        mr.snapshot_id,
        hs.hospital_id,
        mr.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        mr.row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as modifier_payer_ordinal,
        cast(null as varchar) as modifier_code_id,
        mr.raw_modifier_combination as raw_modifier_code,
        mr.clean_modifier_combination as clean_modifier_code,
        mr.raw_description,
        mr.clean_description,
        mr.raw_setting,
        mr.clean_setting,
        cast(null as varchar) as raw_payer_name,
        cast(null as varchar) as clean_payer_name,
        cast(null as varchar) as raw_plan_name,
        cast(null as varchar) as clean_plan_name,
        cast(null as varchar) as raw_payer_description,
        cast(null as varchar) as clean_payer_description,
        cast(null as decimal(18, 4)) as negotiated_dollar,
        cast(null as double) as negotiated_percentage,
        cast(null as varchar) as negotiated_algorithm,
        cast(null as varchar) as raw_methodology,
        cast(null as varchar) as clean_methodology,
        cast(null as decimal(18, 4)) as median_amount,
        cast(null as decimal(18, 4)) as tenth_percentile,
        cast(null as decimal(18, 4)) as ninetieth_percentile,
        cast(null as varchar) as raw_count,
        cast(null as varchar) as additional_generic_notes,
        cast(null as varchar) as additional_payer_notes
    from {{ ref('stg_bronze__csv_modifier_rows') }} mr
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on mr.snapshot_id = hs.snapshot_id
    where mr.is_standalone_modifier
),

csv_modifier_payers as (
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        r.row_ordinal,
        r.source_rate_ordinal,
        r.source_rate_ordinal as modifier_payer_ordinal,
        cast(null as varchar) as modifier_code_id,
        mr.raw_modifier_combination as raw_modifier_code,
        mr.clean_modifier_combination as clean_modifier_code,
        mr.raw_description,
        mr.clean_description,
        mr.raw_setting,
        mr.clean_setting,
        r.raw_payer_name,
        r.clean_payer_name,
        r.raw_plan_name,
        r.clean_plan_name,
        cast(null as varchar) as raw_payer_description,
        cast(null as varchar) as clean_payer_description,
        r.negotiated_dollar,
        r.negotiated_percentage,
        r.negotiated_algorithm,
        r.raw_methodology,
        r.clean_methodology,
        r.median_amount,
        r.tenth_percentile,
        r.ninetieth_percentile,
        r.raw_count,
        r.additional_generic_notes,
        r.additional_payer_notes
    from {{ ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ ref('stg_bronze__csv_modifier_rows') }} mr
        on r.snapshot_id = mr.snapshot_id
        and r.row_ordinal = mr.row_ordinal
        and mr.is_standalone_modifier
    inner join {{ ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    where r.clean_payer_name is not null
        or r.clean_plan_name is not null
        or r.clean_methodology is not null
        or r.negotiated_dollar is not null
        or r.negotiated_percentage is not null
        or {{ hpt_trimmed_text('r.negotiated_algorithm') }} is not null
        or r.median_amount is not null
        or r.tenth_percentile is not null
        or r.ninetieth_percentile is not null
        or {{ hpt_trimmed_text('r.raw_count') }} is not null
        or {{ hpt_trimmed_text('r.additional_generic_notes') }} is not null
        or {{ hpt_trimmed_text('r.additional_payer_notes') }} is not null
),

csv_rule_sufficiency as (
    select
        p.snapshot_id,
        p.row_ordinal,
        bool_or(
            p.negotiated_dollar is not null
            or p.negotiated_percentage is not null
            or {{ hpt_trimmed_text('p.negotiated_algorithm') }} is not null
            or {{ hpt_trimmed_text('p.additional_generic_notes') }} is not null
            or {{ hpt_trimmed_text('p.additional_payer_notes') }} is not null
        ) as has_allowed_alternative
    from csv_modifier_payers p
    group by p.snapshot_id, p.row_ordinal
),

violations as (
    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer) as payer_ordinal, row_ordinal, source_rate_ordinal,
        cast(null as integer) as code_ordinal, modifier_code_id, modifier_payer_ordinal,
        'modifier_required_shape' as rule_id,
        case when clean_modifier_code is null then 'modifier_information.code' else 'modifier_information.description' end as column_name,
        concat('code=', coalesce(raw_modifier_code, '<null>'), '; description=', coalesce(raw_description, '<null>')) as raw_value,
        'required_field_missing' as diagnostic_type,
        'JSON modifier information requires code and description.' as message
    from json_modifiers
    where clean_modifier_code is null or clean_description is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, source_rate_ordinal,
        cast(null as integer), modifier_code_id, modifier_payer_ordinal,
        'modifier_payer_required_shape',
        case
            when clean_payer_name is null then 'modifier_payer_information.payer_name'
            when clean_plan_name is null then 'modifier_payer_information.plan_name'
            else 'modifier_payer_information.description'
        end,
        concat(
            'payer=', coalesce(raw_payer_name, '<null>'),
            '; plan=', coalesce(raw_plan_name, '<null>'),
            '; description=', coalesce(raw_payer_description, '<null>')
        ),
        'required_field_missing',
        'JSON modifier payer information requires payer name, plan name, and description.'
    from json_modifier_payers
    where clean_payer_name is null or clean_plan_name is null or clean_payer_description is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, source_rate_ordinal,
        cast(null as integer), modifier_code_id, modifier_payer_ordinal,
        'modifier_setting_allowed_values', 'modifier_information.setting', raw_setting,
        'accepted_value_invalid',
        'Modifier setting must be inpatient, outpatient, or both when present.'
    from (
        select * from json_modifiers
        union all
        select * from csv_modifier_rules
    ) modifier_rules
    where clean_setting is not null
        and clean_setting not in ('inpatient', 'outpatient', 'both')

    union all

    select
        r.snapshot_id, r.hospital_id, r.source_format, r.source_format_family,
        r.reported_schema_family, r.source_charge_item_id, r.source_standard_charge_id,
        cast(null as integer), r.row_ordinal, r.source_rate_ordinal,
        cast(null as integer), r.modifier_code_id, r.modifier_payer_ordinal,
        'csv_modifier_without_item_minimum_information', 'modifiers', r.raw_modifier_code,
        'conditional_required_field_missing',
        'CSV standalone modifier rules require description plus a negotiated adjustment or note.'
    from csv_modifier_rules r
    left join csv_rule_sufficiency s
        on r.snapshot_id = s.snapshot_id
        and r.row_ordinal = s.row_ordinal
    where r.clean_description is null
        or not coalesce(s.has_allowed_alternative, false)

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, source_charge_item_id, source_standard_charge_id,
        cast(null as integer), row_ordinal, source_rate_ordinal,
        cast(null as integer), modifier_code_id, modifier_payer_ordinal,
        'csv_modifier_payer_context_advisory', 'modifier_payer_context',
        concat(
            'payer=', coalesce(raw_payer_name, '<null>'),
            '; plan=', coalesce(raw_plan_name, '<null>'),
            '; methodology=', coalesce(raw_methodology, '<null>'),
            '; count=', coalesce(raw_count, '<null>')
        ),
        'recommended_context_missing',
        'CSV standalone modifier payer information omits ordinary payer-rate context.'
    from csv_modifier_payers
    where clean_payer_name is null
        or clean_plan_name is null
        or clean_methodology is null
        or (
            (negotiated_percentage is not null or {{ hpt_trimmed_text('negotiated_algorithm') }} is not null)
            and (
                {{ hpt_trimmed_text('raw_count') }} is null
                or median_amount is null
                or tenth_percentile is null
                or ninetieth_percentile is null
            )
        )
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'modifier'", 'v.rule_id', 'v.column_name',
            'v.modifier_code_id', 'v.modifier_payer_ordinal', 'v.row_ordinal',
            'v.source_rate_ordinal', 'v.raw_value'
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
        v.modifier_payer_ordinal,
        cast(null as varchar) as structural_section,
        cast(null as integer) as record_ordinal,
        v.rule_id,
        r.rule_name,
        r.severity,
        case
            when v.rule_id in ('modifier_payer_required_shape', 'csv_modifier_payer_context_advisory') then 'modifier_payer'
            else 'modifier'
        end as grain,
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
