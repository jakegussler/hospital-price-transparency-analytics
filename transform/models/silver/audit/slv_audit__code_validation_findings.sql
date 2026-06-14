-- Code-quality findings from the Silver Core code enrichment, aggregated by
-- hospital, system, and status. Deliberately excludes the not_validated
-- status: CDM/LOCAL systems have no canonical format, so scoring them here
-- would flood the findings with ~1M expected rows. Scoped to current
-- snapshots so superseded snapshots do not double-count under all_snapshots
-- retention. Findings for humans to read, not a review queue.
with current_snapshots as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
    where is_current_snapshot = true
),

offending_codes as (
    select codes.*
    from {{ ref('slv_core__charge_item_codes') }} codes
    inner join current_snapshots
        on codes.snapshot_id = current_snapshots.snapshot_id
    where codes.code_format_status in (
            'invalid_format',
            'unknown_code_system',
            'missing_code',
            'missing_code_system'
        )
        or codes.ndc_format_status in (
            'ambiguous_10_unhyphenated',
            'invalid_layout',
            'invalid_length'
        )
)

select
    hospital_id,
    coalesce(canonical_code_system, clean_code_type, '<missing>') as code_system,
    code_format_status,
    ndc_format_status,
    count(*) as code_rows,
    count(distinct snapshot_id) as snapshot_count,
    count(distinct silver_charge_item_id) as item_count,
    min(clean_code) filter (where clean_code is not null) as example_clean_code,
    min(match_code) filter (where match_code is not null) as example_match_code
from offending_codes
group by hospital_id, code_system, code_format_status, ndc_format_status
order by code_rows desc, hospital_id, code_system
