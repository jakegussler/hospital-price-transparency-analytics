-- gld_score__hospital_transparency_scorecard
--
-- Grain: one row per hospital_id (its current snapshot). Purpose: separate "large
-- file" from "usable comparison coverage" by rolling the per-snapshot coverage
-- scorecard up to a small set of 0–1 readiness scores.
--
-- NAMING CAUTION (carried from planning): this is a TRANSPARENCY / COVERAGE /
-- DATA-READINESS scorecard. The scores measure how much comparable, mapped,
-- dollar-valued data a hospital published — NOT legal compliance. Do not read a
-- compliance verdict from these convenience metrics.
--
-- Reads the per-snapshot gld_score__snapshot_coverage_scorecard, picks each hospital's
-- current snapshot, and joins gld_dim__hospital for descriptive attributes.
-- Full-refresh table (gold.scorecards config block).

with coverage as (
    select *
    from {{ ref('gld_score__snapshot_coverage_scorecard') }}
),

-- One row per hospital: its current snapshot (or, absent one, its freshest).
ranked as (
    select
        *,
        row_number() over (
            partition by hospital_id
            order by is_current_snapshot desc, snapshot_age_days asc nulls last
        ) as rn
    from coverage
),

current_coverage as (
    select *
    from ranked
    where rn = 1
),

scored as (
    select
        c.hospital_id,
        c.snapshot_id,
        c.is_current_snapshot as current_snapshot_available,
        c.freshness_bucket,
        c.snapshot_age_days,

        -- component readiness scores (0–1)
        case c.freshness_bucket
            when '<=90d' then 1.0
            when '<=180d' then 0.75
            when '<=365d' then 0.5
            when '>365d' then 0.25
            else 0.0
        end as freshness_score,
        coalesce(c.coded_item_coverage_rate, 0.0) as code_coverage_score,
        coalesce(c.dollar_observation_coverage_rate, 0.0) as amount_coverage_score,
        coalesce(c.payer_mapping_coverage_rate, 0.0) as payer_mapping_score,
        coalesce(
            c.tier_2_count
                / nullif(c.tier_0_count + c.tier_1_count + c.tier_2_count, 0)::double,
            0.0
        ) as comparison_readiness_score,

        -- carried context for drill-down
        c.charge_item_count,
        c.observation_count,
        c.distinct_comparable_codes,
        c.coded_item_coverage_rate,
        c.dollar_observation_coverage_rate,
        c.payer_mapping_coverage_rate
    from current_coverage as c
)

select
    s.hospital_id,
    h.canonical_hospital_name,
    h.canonical_state,
    h.hospital_type,
    h.health_system,
    s.snapshot_id,
    s.current_snapshot_available,
    s.freshness_bucket,
    s.snapshot_age_days,

    s.freshness_score,
    s.code_coverage_score,
    s.amount_coverage_score,
    s.payer_mapping_score,
    s.comparison_readiness_score,
    -- convenience composite: mean of the five component scores
    (
        s.freshness_score
        + s.code_coverage_score
        + s.amount_coverage_score
        + s.payer_mapping_score
        + s.comparison_readiness_score
    ) / 5.0 as overall_readiness_score,

    s.charge_item_count,
    s.observation_count,
    s.distinct_comparable_codes,
    s.coded_item_coverage_rate,
    s.dollar_observation_coverage_rate,
    s.payer_mapping_coverage_rate
from scored as s
left join {{ ref('gld_dim__hospital') }} as h
    on s.hospital_id = h.hospital_id
