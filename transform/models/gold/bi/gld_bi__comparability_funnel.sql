-- gld_bi__comparability_funnel
--
-- BI presentation surface for the "published vs. comparable" funnel: how many
-- classified price rows survive each cumulative comparability gate. Grain: one
-- row per (scope_level, hospital_id, stage_index), where scope_level is
-- 'hospital' (one funnel per hospital) or 'corpus' (one corpus-wide funnel with
-- the '<corpus>' hospital_id sentinel).
--
-- Rows come from gld_mart__service_price_comparison_current, so the funnel
-- covers CURRENT snapshots at the classified-row grain (observation x
-- comparable-code cohort, tier_0 collapse) — the same "row" vocabulary the
-- blocker summary uses for classified_row_count. Stages are cumulative ANDs of
-- the decision-0017 gates, so each stage is a subset of the previous one by
-- construction (locked by gld_bi_funnel_stage_monotonic.sql):
--
--   1 published_rows        all classified rows in current files
--   2 code_comparable_rows  + a cross-hospital-comparable code
--   3 context_aligned_rows  + specific code and known setting/billing class
--                             (comparison_tier = tier_2_context_aligned)
--   4 rankable_dollar_rows  + a directly rankable dollar amount
--   5 meets_floor_rows      + the exact context has >= 3 reporting hospitals
--
-- Stage 5's extra gate is the cohort-grain below_min_hospital_denominator
-- blocker (decision 0017), evaluated where the peer window is known.

with mart as (
    select
        hospital_id,
        (comparison_tier in ('tier_1_code_backed', 'tier_2_context_aligned'))
            as is_code_comparable,
        (comparison_tier = 'tier_2_context_aligned') as is_context_aligned,
        is_price_ranking_row,
        (is_price_ranking_row and not below_min_hospital_denominator)
            as meets_floor
    from {{ ref('gld_mart__service_price_comparison_current') }}
),

hospital_agg as (
    select
        'hospital' as scope_level,
        hospital_id,
        count(*) as published_rows,
        coalesce(sum(is_code_comparable::int), 0) as code_comparable_rows,
        coalesce(sum(is_context_aligned::int), 0) as context_aligned_rows,
        coalesce(sum(is_price_ranking_row::int), 0) as rankable_dollar_rows,
        coalesce(sum(meets_floor::int), 0) as meets_floor_rows
    from mart
    group by hospital_id
),

corpus_agg as (
    select
        'corpus' as scope_level,
        '<corpus>' as hospital_id,
        count(*) as published_rows,
        coalesce(sum(is_code_comparable::int), 0) as code_comparable_rows,
        coalesce(sum(is_context_aligned::int), 0) as context_aligned_rows,
        coalesce(sum(is_price_ranking_row::int), 0) as rankable_dollar_rows,
        coalesce(sum(meets_floor::int), 0) as meets_floor_rows
    from mart
),

combined as (
    select * from hospital_agg
    union all
    select * from corpus_agg
),

stages as (
    select
        scope_level, hospital_id,
        1 as stage_index,
        'published_rows' as stage_code,
        'Price rows published in current files' as stage_label,
        published_rows as row_count,
        published_rows
    from combined
    union all
    select
        scope_level, hospital_id,
        2,
        'code_comparable_rows',
        'With a code usable across hospitals',
        code_comparable_rows,
        published_rows
    from combined
    union all
    select
        scope_level, hospital_id,
        3,
        'context_aligned_rows',
        'With full service context (setting and billing type)',
        context_aligned_rows,
        published_rows
    from combined
    union all
    select
        scope_level, hospital_id,
        4,
        'rankable_dollar_rows',
        'With a directly rankable dollar price',
        rankable_dollar_rows,
        published_rows
    from combined
    union all
    select
        scope_level, hospital_id,
        5,
        'meets_floor_rows',
        'In a context reported by at least 3 hospitals',
        meets_floor_rows,
        published_rows
    from combined
)

select
    s.scope_level,
    s.hospital_id,
    case
        when s.scope_level = 'corpus' then 'All hospitals'
        else h.canonical_hospital_name
    end as hospital_display_name,
    h.health_system,
    s.stage_index,
    s.stage_code,
    s.stage_label,
    s.row_count,
    s.published_rows as published_row_count,
    s.row_count / nullif(s.published_rows, 0)::double as share_of_published
from stages as s
left join {{ ref('gld_dim__hospital') }} as h
    on s.hospital_id = h.hospital_id
