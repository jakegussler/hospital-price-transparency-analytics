-- Profiling: per-hospital data-readiness scorecard.
-- COVERAGE / READINESS, not legal compliance (see model header). Ranks hospitals
-- by how much comparable, mapped, dollar-valued data they published.
select
    canonical_hospital_name,
    health_system,
    hospital_type,
    freshness_bucket,
    charge_item_count,
    distinct_comparable_codes,
    round(code_coverage_score, 3) as code_coverage_score,
    round(amount_coverage_score, 3) as amount_coverage_score,
    round(payer_mapping_score, 3) as payer_mapping_score,
    round(comparison_readiness_score, 3) as comparison_readiness_score,
    round(overall_readiness_score, 3) as overall_readiness_score
from {{ ref('gld__hospital_transparency_scorecard') }}
order by overall_readiness_score desc
