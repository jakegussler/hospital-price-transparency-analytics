-- Semantic guard (plan §8.2): every readiness score must lie in [0, 1]. A score
-- outside that range means a coverage rate or composite leaked out of bounds.
select *
from {{ ref('gld_score__hospital_transparency_scorecard') }}
where freshness_score not between 0 and 1
    or code_coverage_score not between 0 and 1
    or amount_coverage_score not between 0 and 1
    or payer_mapping_score not between 0 and 1
    or comparison_readiness_score not between 0 and 1
    or overall_readiness_score not between 0 and 1
