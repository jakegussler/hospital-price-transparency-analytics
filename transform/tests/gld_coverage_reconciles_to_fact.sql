-- Reconciliation (plan §10.5): the coverage scorecard's atomic observation count
-- per snapshot must equal the fact's row count per snapshot, and every snapshot in
-- the fact must appear in the scorecard (and vice versa). Any mismatch fails.
with fact_counts as (
    select snapshot_id, count(*) as fact_observation_count
    from {{ ref('gld_core__rate_observations') }}
    group by snapshot_id
),

scorecard_counts as (
    select snapshot_id, observation_count
    from {{ ref('gld__snapshot_coverage_scorecard') }}
)

select
    coalesce(f.snapshot_id, s.snapshot_id) as snapshot_id,
    f.fact_observation_count,
    s.observation_count
from fact_counts as f
full outer join scorecard_counts as s
    on f.snapshot_id = s.snapshot_id
where f.snapshot_id is null
    or s.snapshot_id is null
    or f.fact_observation_count <> s.observation_count
