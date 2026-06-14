with unresolved_code_systems as (
    select
        codes.clean_code_type,
        codes.raw_code_type,
        codes.clean_code,
        codes.raw_code,
        codes.hospital_id,
        codes.snapshot_id,
        codes.source_format
    from {{ ref('slv_base__charge_item_codes') }} codes
    where codes.clean_code_type is not null
        and codes.canonical_code_system is null
        and codes.snapshot_id in (
            {{ hpt_current_snapshot_ids_sql() }}
        )
),

grouped as (
    select
        clean_code_type,
        count(*) as code_rows,
        count(distinct hospital_id) as hospital_count,
        count(distinct snapshot_id) as snapshot_count,
        count(distinct source_format) as source_format_count,
        count(distinct clean_code) filter (where clean_code is not null) as distinct_clean_codes,
        min(raw_code_type) as example_raw_code_type,
        min(clean_code) filter (where clean_code is not null) as example_clean_code,
        min(raw_code) filter (where raw_code is not null) as example_raw_code
    from unresolved_code_systems
    group by clean_code_type
)

select
    {{ hpt_surrogate_key(['clean_code_type']) }} as code_system_candidate_key,
    clean_code_type,
    example_raw_code_type,
    example_clean_code,
    example_raw_code,
    code_rows,
    hospital_count,
    snapshot_count,
    source_format_count,
    distinct_clean_codes,
    'needs_review' as review_queue_status
from grouped
order by
    code_rows desc,
    hospital_count desc,
    clean_code_type
