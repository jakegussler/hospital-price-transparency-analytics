{{ config(tags=['silver_core']) }}

-- Methodology and methodology_basis must agree with the shared canonicalizer.
with expected as (
    select
        silver_payer_rate_id,
        clean_methodology,
        methodology,
        methodology_basis,
        coalesce({{ hpt_canonical_methodology('clean_methodology') }}, 'unmapped') as expected_methodology,
        case
            when {{ hpt_canonical_methodology('clean_methodology') }} is null then 'unmapped'
            when {{ hpt_canonical_methodology('clean_methodology') }} = {{ hpt_clean_text('clean_methodology') }} then 'cms_value'
            else 'mapped'
        end as expected_methodology_basis
    from {{ hpt_scoped_ref('slv_core__payer_rates') }}
)

select
    silver_payer_rate_id,
    clean_methodology,
    methodology,
    expected_methodology,
    methodology_basis,
    expected_methodology_basis
from expected
where methodology is distinct from expected_methodology
    or methodology_basis is distinct from expected_methodology_basis
