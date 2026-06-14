-- Targeted invariants on the derived code-matching fields: fixed-width systems
-- are actually padded, hospital-local systems are never cross-hospital
-- comparable, NDC canonicalization never guesses, and present codes always get
-- a match key.
select
    silver_charge_item_code_id,
    canonical_code_system,
    clean_code,
    match_code,
    code_format_status,
    ndc_format_status,
    canonical_ndc_11
from {{ hpt_scoped_ref('slv_core__charge_item_codes') }}
where
    (
        canonical_code_system = 'rc'
        and regexp_matches(clean_code, '^[0-9]{1,4}$')
        and not regexp_matches(match_code, '^[0-9]{4}$')
    )
    or (
        canonical_code_system in (
            'drg', 'ms-drg', 'r-drg', 's-drg', 'aps-drg',
            'ap-drg', 'apr-drg', 'tris-drg', 'ms-ltc-drg'
        )
        and regexp_matches(clean_code, '^[0-9]{1,3}$')
        and not regexp_matches(match_code, '^[0-9]{3}$')
    )
    or (
        canonical_code_system in ('cdm', 'local')
        and code_cross_hospital_comparable
    )
    or (
        ndc_format_status in ('ambiguous_10_unhyphenated', 'invalid_layout', 'invalid_length')
        and canonical_ndc_11 is not null
    )
    or (
        canonical_ndc_11 is not null
        and not regexp_matches(canonical_ndc_11, '^[0-9]{11}$')
    )
    or (clean_code is not null and match_code is null)
    or (clean_code is null and match_code is not null)
