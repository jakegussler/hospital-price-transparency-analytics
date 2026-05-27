with payer_values as (
    select
        pr.clean_payer_name,
        pr.raw_payer_name,
        pr.clean_plan_name,
        pr.hospital_id,
        pr.snapshot_id,
        pr.source_format,
        core.canonical_payer_id,
        core.payer_match_basis,
        core.payer_review_status
    from {{ ref('slv_base__payer_rates') }} pr
    left join {{ ref('slv_core__payer_rates') }} core
        on pr.silver_payer_rate_id = core.silver_payer_rate_id
    where pr.clean_payer_name is not null
),

grouped as (
    select
        clean_payer_name,
        canonical_payer_id,
        payer_match_basis,
        payer_review_status,
        count(*) as payer_rate_rows,
        count(distinct hospital_id) as hospital_count,
        count(distinct snapshot_id) as snapshot_count,
        count(distinct source_format) as source_format_count,
        count(distinct clean_plan_name) as distinct_clean_plan_names,
        min(raw_payer_name) as example_raw_payer_name,
        min(clean_plan_name) filter (where clean_plan_name is not null) as example_clean_plan_name
    from payer_values
    group by
        clean_payer_name,
        canonical_payer_id,
        payer_match_basis,
        payer_review_status
)

select
    {{ hpt_surrogate_key([
        'clean_payer_name',
        'canonical_payer_id',
        'payer_match_basis',
        'payer_review_status'
    ]) }} as payer_candidate_key,
    clean_payer_name,
    example_raw_payer_name,
    example_clean_plan_name,
    payer_rate_rows,
    hospital_count,
    snapshot_count,
    source_format_count,
    distinct_clean_plan_names,
    canonical_payer_id,
    coalesce(payer_match_basis, 'unmatched') as payer_match_basis,
    coalesce(payer_review_status, 'candidate') as payer_review_status,
    case
        when canonical_payer_id is null then 'needs_review'
        else 'mapped'
    end as review_queue_status
from grouped
order by
    case when canonical_payer_id is null then 0 else 1 end,
    payer_rate_rows desc,
    hospital_count desc,
    clean_payer_name
