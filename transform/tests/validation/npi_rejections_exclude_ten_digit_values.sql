select
    snapshot_id,
    raw_value
from {{ ref('val__all_violations') }}
where rule_id = 'type_2_npi_ten_digit_numeric'
    and regexp_matches({{ hpt_clean_display_text('raw_value') }}, '^[0-9]{10}$')
