-- Emit code-level violations. The normalized code grain (JSON objects + CSV
-- pairs + code-type seed join) is built once in val_int__code_grain; here we
-- scan it a single time and emit one row per (code, violated rule) via a struct
-- list + unnest, instead of re-scanning the grain once per rule. The
-- "CSV charge row with charge data but no code pair" case (csv_code_pair_required)
-- is a charge-item-grain rejection -- it has no code_ordinal, so it cannot drive
-- the code-rejection join -- and lives in val__charge_item_violations, where it
-- routes through the charge-item exclusion path. See docs/cleanup.md.
with code_rows as (
    select * from {{ hpt_scoped_ref('val_int__code_grain') }}
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
),

deduped as (
    -- CSV-wide Bronze is at charge x payer grain, so a single source row's codes
    -- repeat once per payer. Collapse to one violation per source code / row,
    -- rule, column, and raw value -- the same dedup
    -- val__standard_charge_violations applies for the identical reason.
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
