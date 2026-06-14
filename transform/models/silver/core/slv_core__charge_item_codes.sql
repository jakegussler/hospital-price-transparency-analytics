with base_codes as (
    select
        silver_charge_item_code_id,
        silver_charge_item_id,
        snapshot_id,
        hospital_id,
        source_format,
        code_ordinal,
        raw_code,
        clean_code,
        raw_code_type,
        clean_code_type,
        canonical_code_system,
        source_code_path
    from {{ hpt_scoped_ref('slv_base__charge_item_codes') }}
),

ndc_codes as (
    select
        silver_charge_item_code_id,
        clean_code,
        regexp_replace(clean_code, '[^0-9]', '', 'g') as clean_ndc
    from base_codes
    where canonical_code_system = 'ndc'
        and clean_code is not null
),

-- 10-digit padding is certain only when the hyphen layout discloses which
-- segment is short (4-4-2, 5-3-2, 5-4-1). Other 10-digit shapes are flagged,
-- never guessed.
ndc_canonical as (
    select
        silver_charge_item_code_id,
        clean_ndc,
        case
            when length(clean_ndc) = 11
                then clean_ndc
            when regexp_matches(clean_code, '^[0-9]{4}-[0-9]{4}-[0-9]{2}$')
                then '0' || clean_ndc
            when regexp_matches(clean_code, '^[0-9]{5}-[0-9]{3}-[0-9]{2}$')
                then substr(clean_ndc, 1, 5) || '0' || substr(clean_ndc, 6)
            when regexp_matches(clean_code, '^[0-9]{5}-[0-9]{4}-[0-9]$')
                then substr(clean_ndc, 1, 9) || '0' || substr(clean_ndc, 10)
        end as canonical_ndc_11,
        case
            when regexp_matches(clean_code, '^[0-9]{11}$')
                then 'canonical_11_unhyphenated'
            when length(clean_ndc) = 11
                then 'canonical_11'
            when regexp_matches(clean_code, '^[0-9]{4}-[0-9]{4}-[0-9]{2}$')
                then 'padded_from_10_4_4_2'
            when regexp_matches(clean_code, '^[0-9]{5}-[0-9]{3}-[0-9]{2}$')
                then 'padded_from_10_5_3_2'
            when regexp_matches(clean_code, '^[0-9]{5}-[0-9]{4}-[0-9]$')
                then 'padded_from_10_5_4_1'
            when regexp_matches(clean_code, '^[0-9]{10}$')
                then 'ambiguous_10_unhyphenated'
            when length(clean_ndc) = 10
                then 'invalid_layout'
            else 'invalid_length'
        end as ndc_format_status
    from ndc_codes
),

enriched_codes as (
    select
        base_codes.silver_charge_item_code_id,
        base_codes.silver_charge_item_id,
        base_codes.snapshot_id,
        base_codes.hospital_id,
        base_codes.source_format,
        base_codes.code_ordinal,
        base_codes.raw_code,
        base_codes.clean_code,
        base_codes.raw_code_type,
        base_codes.clean_code_type,
        base_codes.canonical_code_system,
        base_codes.source_code_path,
        case
            when base_codes.clean_code is null then null
            when base_codes.canonical_code_system = 'rc'
                 and regexp_matches(base_codes.clean_code, '^[0-9]{1,4}$')
                then lpad(base_codes.clean_code, 4, '0')
            when base_codes.canonical_code_system in (
                    'drg', 'ms-drg', 'r-drg', 's-drg', 'aps-drg',
                    'ap-drg', 'apr-drg', 'tris-drg', 'ms-ltc-drg'
                )
                 and regexp_matches(base_codes.clean_code, '^[0-9]{1,3}$')
                then lpad(base_codes.clean_code, 3, '0')
            when base_codes.canonical_code_system = 'apc'
                 and regexp_matches(base_codes.clean_code, '^[0-9]{1,4}$')
                then lpad(base_codes.clean_code, 4, '0')
            when base_codes.canonical_code_system = 'apc'
                 and regexp_matches(base_codes.clean_code, '^0[0-9]{4}$')
                then substr(base_codes.clean_code, 2)
            when base_codes.canonical_code_system = 'ndc'
                 and ndc_canonical.canonical_ndc_11 is not null
                then ndc_canonical.canonical_ndc_11
            else upper(regexp_replace(base_codes.clean_code, '\s+', '', 'g'))
        end as match_code,
        coalesce(
            base_codes.canonical_code_system not in ('cdm', 'local'),
            false
        ) as code_cross_hospital_comparable,
        -- Specific codes pin down one item; categorical codes (revenue, CDM,
        -- LOCAL) are categories that span thousands of items, and ICD is a
        -- diagnosis, not a service. Whitelist so unrecognized systems default
        -- to the safe value: non-specific identity falls back to the full code
        -- set plus description, which never over-merges.
        coalesce(
            base_codes.canonical_code_system in (
                'cpt', 'hcpcs', 'ndc', 'cdt', 'apc', 'eapg', 'hipps', 'cmg',
                'drg', 'ms-drg', 'r-drg', 's-drg', 'aps-drg',
                'ap-drg', 'apr-drg', 'tris-drg', 'ms-ltc-drg'
            ),
            false
        ) as code_is_specific,
        ndc_canonical.clean_ndc,
        ndc_canonical.canonical_ndc_11,
        ndc_canonical.ndc_format_status
    from base_codes
    left join ndc_canonical
        on base_codes.silver_charge_item_code_id = ndc_canonical.silver_charge_item_code_id
)

select
    *,
    case
        when clean_code is null then 'missing_code'
        when clean_code_type is null then 'missing_code_system'
        when canonical_code_system is null then 'unknown_code_system'
        when canonical_code_system = 'rc' then
            case
                when regexp_matches(match_code, '^[0-9]{4}$') then 'valid'
                else 'invalid_format'
            end
        when canonical_code_system = 'ms-drg' then
            case
                when regexp_matches(match_code, '^[0-9]{3}$') then 'valid'
                else 'invalid_format'
            end
        when canonical_code_system = 'cpt' then
            case
                when regexp_matches(match_code, '^[0-9]{4}[0-9A-Z]$') then 'valid'
                else 'invalid_format'
            end
        when canonical_code_system = 'hcpcs' then
            case
                when regexp_matches(match_code, '^([A-Z][0-9]{4}|[0-9]{4}[0-9A-Z])$') then 'valid'
                else 'invalid_format'
            end
        when canonical_code_system = 'ndc' then
            case
                when canonical_ndc_11 is not null then 'valid'
                else 'invalid_format'
            end
        else 'not_validated'
    end as code_format_status
from enriched_codes
