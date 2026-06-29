-- Profiling: blocker-reason distribution.
-- How many comparison rows fall to each blocker, and how many are fully clear?
select
    count(*) as total_comparison_rows,
    sum((len(blocker_reasons) = 0)::int) as fully_clear_rows,
    sum(not_current_snapshot::int) as not_current_snapshot,
    sum(code_not_cross_hospital_comparable::int) as code_not_cross_hospital_comparable,
    sum(code_not_specific::int) as code_not_specific,
    sum(missing_match_code::int) as missing_match_code,
    sum(non_rankable_amount::int) as non_rankable_amount,
    sum(derived_dollar::int) as derived_dollar,
    sum(modifier_context_required::int) as modifier_context_required,
    sum(drug_unit_context_missing::int) as drug_unit_context_missing,
    sum(payer_unmatched::int) as payer_unmatched,
    sum(market_segment_unknown::int) as market_segment_unknown,
    sum(below_min_hospital_denominator::int) as below_min_hospital_denominator
from {{ ref('gld_mart__service_price_comparison_current') }}
