-- Staging view over the CMS MS-DRG reference table.
-- Shapes the raw reference parquet to the (canonical_code_system, match_code)
-- join keys Silver/Gold use for the DRG family: match_code is the 3-digit
-- zero-padded DRG, matching slv_core__charge_item_codes.
with src as (
    select * from {{ source('reference', 'ms_drg') }}
)

select
    'ms-drg' as canonical_code_system,
    lpad(trim(code), 3, '0') as match_code,
    description as code_description,
    code_edition,
    effective_start,
    effective_end,
    mdc,
    drg_type,
    relative_weight,
    geometric_mean_los,
    arithmetic_mean_los,
    post_acute_drg,
    special_pay_drg,
    source as code_description_source,
    license as code_description_license,
    source_url,
    retrieved_at
from src
