{% set cms_v3_attestation = "To the best of its knowledge and belief, this hospital has included all applicable standard charge information in accordance with the requirements of 45 CFR 180.50, and the information encoded is true, accurate, and complete as of the date in the file. This hospital has included all payer-specific negotiated charges in dollars that can be expressed as a dollar amount. For payer-specific negotiated charges that cannot be expressed as a dollar amount in the machine-readable file or not knowable in advance, the hospital attests that the payer-specific negotiated charge is based on a contractual algorithm, percentage or formula that precludes the provision of a dollar amount and has provided all necessary information available to the hospital for the public to be able to derive the dollar amount, including, but not limited to, the specific fee schedule or components referenced in such percentage, algorithm or formula." %}
{% set cms_v2_affirmation = "To the best of its knowledge and belief, the hospital has included all applicable standard charge information in accordance with the requirements of 45 CFR 180.50, and the information encoded is true, accurate, and complete as of the date indicated." %}

with snapshots as (
    select
        s.*,
        {{ hpt_source_format_family('s.source_format') }} as source_format_family,
        coalesce({{ hpt_schema_family_from_version('s.schema_version') }}, '3.0') as reported_schema_family
    from {{ ref('stg_bronze__hospital_mrf_snapshots') }} s
),

npi_counts as (
    select snapshot_id, count(*) as npi_count
    from {{ ref('stg_bronze__type2_npi') }}
    group by snapshot_id
),

json_charge_counts as (
    select snapshot_id, count(*) as charge_count
    from {{ ref('stg_bronze__standard_charge_info') }}
    group by snapshot_id
),

csv_charge_counts as (
    select snapshot_id, count(distinct row_ordinal) as charge_count
    from {{ ref('stg_bronze__csv_charge_rows') }}
    group by snapshot_id
),

snapshot_context as (
    select
        s.*,
        coalesce(n.npi_count, 0) as npi_count,
        case
            when s.source_format_family = 'json' then coalesce(j.charge_count, 0)
            when s.source_format_family = 'csv' then coalesce(c.charge_count, 0)
            else 0
        end as charge_count
    from snapshots s
    left join npi_counts n on s.snapshot_id = n.snapshot_id
    left join json_charge_counts j on s.snapshot_id = j.snapshot_id
    left join csv_charge_counts c on s.snapshot_id = c.snapshot_id
),

npi_values as (
    select
        n.snapshot_id,
        s.hospital_id,
        s.source_format,
        s.source_format_family,
        s.reported_schema_family,
        n.npi_ordinal,
        n.raw_npi,
        n.clean_npi
    from {{ ref('stg_bronze__type2_npi') }} n
    inner join snapshots s on n.snapshot_id = s.snapshot_id
),

violations as (
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        cast(null as integer) as row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'root_required_header_shape' as rule_id,
        column_name,
        raw_value,
        'required_field_missing' as diagnostic_type,
        column_name || ' is required at the file/header grain.' as message
    from snapshot_context,
    lateral (
        values
            ('hospital_name', raw_reported_hospital_name, clean_reported_hospital_name is null),
            ('last_updated_on', raw_published_last_updated_on, raw_published_last_updated_on is null),
            ('version', schema_version, {{ hpt_clean_display_text('schema_version') }} is null),
            ('license_information.state', reported_state, {{ hpt_clean_display_text('reported_state') }} is null),
            ('type_2_npi', cast(npi_count as varchar), npi_count = 0),
            ('standard_charge_information', cast(charge_count as varchar), charge_count = 0)
    ) missing(column_name, raw_value, is_violation)
    where is_violation

    union all

    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        cast(null as varchar),
        cast(null as varchar),
        cast(null as integer),
        cast(null as integer),
        cast(null as integer),
        cast(null as integer),
        cast(null as varchar),
        'attestation_required_fields' as rule_id,
        column_name,
        raw_value,
        'required_field_missing' as diagnostic_type,
        column_name || ' is required for the reported JSON schema family.' as message
    from snapshot_context,
    lateral (
        values
            ('attestation.attestation', attestation, source_format_family = 'json' and reported_schema_family = '3.0' and {{ hpt_clean_display_text('attestation') }} is null),
            ('attestation.confirm_attestation', confirm_attestation, source_format_family = 'json' and reported_schema_family = '3.0' and {{ hpt_clean_display_text('confirm_attestation') }} is null),
            ('attestation.attester_name', attester_name, source_format_family = 'json' and reported_schema_family = '3.0' and {{ hpt_clean_display_text('attester_name') }} is null),
            ('affirmation.affirmation', affirmation, source_format_family = 'json' and reported_schema_family in ('2.1', '2.2') and {{ hpt_clean_display_text('affirmation') }} is null),
            ('affirmation.confirm_affirmation', confirm_affirmation, source_format_family = 'json' and reported_schema_family in ('2.1', '2.2') and {{ hpt_clean_display_text('confirm_affirmation') }} is null)
    ) missing(column_name, raw_value, is_violation)
    where is_violation

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'license_information_required_state', 'license_information.state',
        reported_state, 'required_field_missing',
        'License state is required.'
    from snapshot_context
    where {{ hpt_clean_display_text('reported_state') }} is null

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'last_updated_on_iso_date', 'last_updated_on',
        raw_published_last_updated_on, 'date_format_invalid',
        'MRF date is not in an accepted source-format-specific format.'
    from snapshot_context
    where raw_published_last_updated_on is not null
        and (
            (
                source_format_family = 'json'
                and not regexp_matches({{ hpt_clean_display_text('raw_published_last_updated_on') }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
            )
            or (
                source_format_family = 'csv'
                and not (
                    regexp_matches({{ hpt_clean_display_text('raw_published_last_updated_on') }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
                    or regexp_matches({{ hpt_clean_display_text('raw_published_last_updated_on') }}, '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}$')
                )
            )
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'state_two_letter_format', 'license_information.state',
        reported_state, 'state_format_invalid',
        'License state must be exactly two alphabetic characters.'
    from snapshot_context
    where {{ hpt_clean_display_text('reported_state') }} is not null
        and not regexp_matches({{ hpt_clean_display_text('reported_state') }}, '^[A-Za-z]{2}$')

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'state_valid_usps_code', 'license_information.state',
        reported_state, 'accepted_value_invalid',
        'License state is not in the CMS state and territory abbreviation list.'
    from snapshot_context
    where regexp_matches({{ hpt_clean_display_text('reported_state') }}, '^[A-Za-z]{2}$')
        and not exists (
            select 1
            from {{ ref('states') }} states
            where states.state_code = upper({{ hpt_clean_display_text('reported_state') }})
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'attestation_text_exact',
        case when reported_schema_family = '3.0' then 'attestation' else 'affirmation' end,
        case when reported_schema_family = '3.0' then attestation else affirmation end,
        'attestation_text_mismatch',
        'Attestation or affirmation text does not match the CMS-required statement.'
    from snapshot_context
    where (
            reported_schema_family = '3.0'
            and {{ hpt_clean_display_text('attestation') }} is not null
            and regexp_replace({{ hpt_clean_display_text('attestation') }}, '\\s+', ' ', 'g') != '{{ cms_v3_attestation }}'
        )
        or (
            reported_schema_family in ('2.1', '2.2')
            and {{ hpt_clean_display_text('affirmation') }} is not null
            and regexp_replace({{ hpt_clean_display_text('affirmation') }}, '\\s+', ' ', 'g') != '{{ cms_v2_affirmation }}'
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'attestation_confirmation_true',
        case when reported_schema_family = '3.0' then 'confirm_attestation' else 'confirm_affirmation' end,
        case when reported_schema_family = '3.0' then confirm_attestation else confirm_affirmation end,
        'attestation_confirmation_not_true',
        'Attestation confirmation must be true.'
    from snapshot_context
    where (
            reported_schema_family = '3.0'
            and {{ hpt_clean_display_text('confirm_attestation') }} is not null
            and lower({{ hpt_clean_display_text('confirm_attestation') }}) not in ('true', '1', 'yes')
        )
        or (
            reported_schema_family in ('2.1', '2.2')
            and {{ hpt_clean_display_text('confirm_affirmation') }} is not null
            and lower({{ hpt_clean_display_text('confirm_affirmation') }}) not in ('true', '1', 'yes')
        )

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'required_header_text_non_empty', column_name, raw_value,
        'required_text_blank',
        column_name || ' is required and must not be blank.'
    from snapshot_context,
    lateral (
        values
            ('hospital_name', raw_reported_hospital_name),
            ('last_updated_on', raw_published_last_updated_on),
            ('version', schema_version),
            ('license_information.state', reported_state)
    ) required_text(column_name, raw_value)
    where raw_value is not null and trim(cast(raw_value as varchar)) = ''

    union all

    select
        snapshot_id, hospital_id, source_format, source_format_family,
        reported_schema_family, cast(null as varchar), cast(null as varchar),
        cast(null as integer), cast(null as integer), cast(null as integer),
        cast(null as integer), cast(null as varchar),
        'csv_placeholder_headers_resolved', column_name, raw_value,
        'csv_placeholder_unresolved',
        'CSV placeholder token appears unresolved in a parsed header value.'
    from snapshot_context,
    lateral (
        values
            ('license_number|[state]', license_number),
            ('attestation', attestation)
    ) placeholder_values(column_name, raw_value)
    where source_format_family = 'csv'
        and raw_value is not null
        and regexp_matches(cast(raw_value as varchar), '\\[[A-Za-z_]+\\]')
),

enriched as (
    select
        {{ hpt_surrogate_key([
            'v.snapshot_id', "'header'", 'v.rule_id', 'v.column_name',
            'v.raw_value', 'v.source_charge_item_id', 'v.source_standard_charge_id',
            'v.row_ordinal', 'v.source_rate_ordinal', 'v.code_ordinal',
            'v.modifier_code_id'
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
        'header' as grain,
        r.disposition,
        v.column_name,
        v.raw_value,
        v.diagnostic_type,
        v.message,
        r.disposition = 'exclude_entity' as is_rejected,
        r.disposition = 'exclude_entity' as excludes_from_silver,
        r.cms_citation
    from violations v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
