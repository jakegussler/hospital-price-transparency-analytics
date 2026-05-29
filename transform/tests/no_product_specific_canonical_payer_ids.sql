select *
from {{ ref('canonical_payers') }}
where active = true
    and regexp_matches(
        canonical_payer_id,
        '(_unknown|_commercial|_medicare_advantage|_medicaid|_exchange|_workers_comp|_community_plan|_better_health|_whole_health|_blueadvantage|_bluecare_plus)$'
    )
