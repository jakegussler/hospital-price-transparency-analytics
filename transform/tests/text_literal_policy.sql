{{ config(tags=['staging', 'validation']) }}

with cases as (
    select
        *
    from (
        values
            ('sql_null', cast(null as varchar), cast(null as varchar), cast(null as varchar), true, true),
            ('blank', '   ', cast(null as varchar), cast(null as varchar), true, true),
            ('n_a', ' N/A ', 'N/A', 'n/a', true, true),
            ('dash', ' - ', '-', '-', true, true),
            ('none', ' None ', 'None', 'none', true, true),
            ('unknown', ' Unknown ', 'Unknown', 'unknown', true, true),
            ('normal', ' Mixed   Case ', 'Mixed   Case', 'mixed case', true, false),
            ('numeric', ' 42.5 ', '42.5', '42.5', false, false)
    ) as t(
        case_name,
        input_value,
        expected_trimmed,
        expected_normalized,
        expected_decimal_is_null,
        expected_sentinel_is_null
    )
),

actual as (
    select
        *,
        {{ hpt_trimmed_text('input_value') }} as actual_trimmed,
        {{ hpt_normalize_text('input_value') }} as actual_normalized,
        {{ hpt_safe_decimal('input_value') }} is null as actual_decimal_is_null,
        {{ hpt_nullify_sentinel_text('input_value') }} is null as actual_sentinel_is_null
    from cases
)

select *
from actual
where actual_trimmed is distinct from expected_trimmed
    or actual_normalized is distinct from expected_normalized
    or actual_decimal_is_null is distinct from expected_decimal_is_null
    or actual_sentinel_is_null is distinct from expected_sentinel_is_null
