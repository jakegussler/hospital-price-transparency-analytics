-- Emit code-level and missing-CSV-code violations. The normalized code grain
-- (JSON objects + CSV pairs + code-type seed join) is built once in
-- val_int__code_grain; here we scan it a single time and emit one row per
-- (code, violated rule) via a struct list + unnest, instead of re-scanning the
-- grain once per rule. The missing-code rule is a different (row) grain, so it
-- stays a separate branch. See docs/cleanup.md.
with code_rows as (
    select * from {{ hpt_scoped_ref('val_int__code_grain') }}
),

csv_rows_without_codes as (
    -- Rows with charge data but no code pair cannot appear in the code-grain
    -- union, so retain them separately for the CSV conditional rule. The
    -- anti-join uses the pre-materialized unpivot rather than re-running it.
    select
        r.snapshot_id,
        hs.hospital_id,
        r.source_format,
        'csv' as source_format_family,
        '3.0' as reported_schema_family,
        r.row_ordinal
    from {{ hpt_scoped_ref('stg_bronze__csv_charge_rows') }} r
    inner join {{ hpt_scoped_ref('stg_bronze__hospital_mrf_snapshots') }} hs
        on r.snapshot_id = hs.snapshot_id
    left join {{ hpt_scoped_ref('val_int__csv_code_pairs') }} p
        on r.snapshot_id = p.snapshot_id
        and r.row_ordinal = p.row_ordinal
    where p.row_ordinal is null
        and (
            r.gross_charge is not null
            or r.discounted_cash is not null
            or r.negotiated_dollar is not null
            or r.negotiated_percentage is not null
            or r.negotiated_algorithm is not null
        )
),

evaluated as (
    -- One scan of the code grain. Each rule contributes a struct when it fires.
    select
        cr.*,
        list_filter([
            -- Required shape: code and type must be present as a pair.
            case
                when clean_code is null or clean_code_type is null
                then struct_pack(
                    rule_id := 'code_information_required_shape',
                    column_name := case when clean_code is null then 'code' else 'type' end,
                    raw_value := coalesce(raw_code, raw_code_type),
                    diagnostic_type := 'code_pair_incomplete',
                    message := 'Code and code type must be present as a pair.'
                )
            end,
            -- Accepted-value: code type must be in the project-wide value set.
            case
                when clean_code_type is not null and matched_code_type is null
                then struct_pack(
                    rule_id := 'code_type_allowed_values',
                    column_name := 'code_type',
                    raw_value := raw_code_type,
                    diagnostic_type := 'accepted_value_invalid',
                    message := 'Code type is not in the project-wide CMS code type value set.'
                )
            end,
            -- Family-specific accepted-value: valid globally but not for the
            -- reported schema family.
            case
                when matched_code_type is not null
                    and (
                        (reported_schema_family = '2.1' and not valid_in_2_1)
                        or (reported_schema_family = '2.2' and not valid_in_2_2)
                        or (reported_schema_family = '3.0' and not valid_in_3_0)
                    )
                then struct_pack(
                    rule_id := 'code_type_family_specific_enum',
                    column_name := 'code_type',
                    raw_value := raw_code_type,
                    diagnostic_type := 'family_accepted_value_invalid',
                    message := 'Code type is valid globally but not for the reported schema family.'
                )
            end,
            -- Non-empty text: required code fields must not be blank.
            case
                when (raw_code is not null and trim(cast(raw_code as varchar)) = '')
                    or (raw_code_type is not null and trim(cast(raw_code_type as varchar)) = '')
                then struct_pack(
                    rule_id := 'code_text_non_empty',
                    column_name := case
                        when raw_code is not null and trim(cast(raw_code as varchar)) = '' then 'code'
                        else 'type'
                    end,
                    raw_value := case
                        when raw_code is not null and trim(cast(raw_code as varchar)) = '' then raw_code
                        else raw_code_type
                    end,
                    diagnostic_type := 'required_text_blank',
                    message := 'Required code fields must not be blank.'
                )
            end
        ], x -> x is not null) as rule_hits
    from code_rows cr
),

violations as (
    -- Code-grain rules, one row per (code, violated rule).
    select
        e.snapshot_id,
        e.hospital_id,
        e.source_format,
        e.source_format_family,
        e.reported_schema_family,
        e.source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        e.row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        e.code_ordinal,
        cast(null as varchar) as modifier_code_id,
        hit.rule_id,
        hit.column_name,
        hit.raw_value,
        hit.diagnostic_type,
        hit.message
    from evaluated e
    cross join unnest(e.rule_hits) as t(hit)

    union all

    -- CSV charge rows that are missing every code/code-type pair (row grain).
    select
        snapshot_id,
        hospital_id,
        source_format,
        source_format_family,
        reported_schema_family,
        cast(null as varchar) as source_charge_item_id,
        cast(null as varchar) as source_standard_charge_id,
        cast(null as integer) as payer_ordinal,
        row_ordinal,
        cast(null as integer) as source_rate_ordinal,
        cast(null as integer) as code_ordinal,
        cast(null as varchar) as modifier_code_id,
        'csv_code_pair_required' as rule_id,
        'code|[i]' as column_name,
        cast(null as varchar) as raw_value,
        'csv_code_pair_missing' as diagnostic_type,
        'CSV charge row has charge data but no code/code-type pair.' as message
    from csv_rows_without_codes
),

deduped as (
    -- CSV-wide Bronze is at charge x payer grain, so a single source row's codes
    -- (and its missing-code finding) repeat once per payer. Collapse to one
    -- violation per source code / row, rule, column, and raw value -- the same
    -- dedup val__standard_charge_violations applies for the identical reason.
    select *
    from violations
    qualify row_number() over (
        partition by
            snapshot_id,
            source_format_family,
            coalesce(source_charge_item_id, ''),
            coalesce(cast(row_ordinal as varchar), ''),
            coalesce(cast(code_ordinal as varchar), ''),
            rule_id,
            column_name,
            coalesce(raw_value, '')
        order by 1
    ) = 1
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
    from deduped v
    inner join {{ ref('cms_validation_rules') }} r
        on v.rule_id = r.rule_id
)

select * from enriched
