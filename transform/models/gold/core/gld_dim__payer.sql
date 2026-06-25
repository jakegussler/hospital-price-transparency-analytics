-- Conformed payer dimension. Grain: one row per canonical_payer_id.
--
-- Source: the canonical_payers seed (the authoritative payer master). Only
-- STABLE payer attributes live here. Row-level context resolved per rate
-- (market_segment, benefit_line, plan_type) is a property of the *observation*,
-- not the payer, so it stays on the fact and never on this dimension. Full-refresh
-- table read unscoped.
--
-- An explicit <unmatched> member lets standard-charge-scope and unmatched
-- payer-rate observations join without losing rows. Per decision 0017 the
-- unmatched member appears in coverage scorecards but never in payer benchmark
-- math; is_unmatched_member makes that exclusion a column, not a magic string.
with seeded as (
    select
        canonical_payer_id,
        canonical_payer_name,
        payer_parent_id,
        payer_parent_name,
        payer_type,
        false as is_unmatched_member
    from {{ ref('canonical_payers') }}
),

unmatched_member as (
    select
        '<unmatched>' as canonical_payer_id,
        'Unmatched payer' as canonical_payer_name,
        cast(null as varchar) as payer_parent_id,
        cast(null as varchar) as payer_parent_name,
        'unmatched' as payer_type,
        true as is_unmatched_member
)

select * from seeded
union all
select * from unmatched_member
