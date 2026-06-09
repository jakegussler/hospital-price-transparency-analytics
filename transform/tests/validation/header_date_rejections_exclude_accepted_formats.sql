select
    snapshot_id,
    source_format_family,
    raw_value
from {{ ref('val__all_violations') }}
where rule_id = 'last_updated_on_iso_date'
    and (
        (
            source_format_family = 'json'
            and regexp_matches({{ hpt_trimmed_text('raw_value') }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
        )
        or (
            source_format_family = 'csv'
            and (
                regexp_matches({{ hpt_trimmed_text('raw_value') }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
                or regexp_matches({{ hpt_trimmed_text('raw_value') }}, '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}$')
            )
        )
    )
