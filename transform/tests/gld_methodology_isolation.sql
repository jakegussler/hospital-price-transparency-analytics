-- Methodology isolation (decision 0021): no market cohort may mix negotiated
-- methodologies, and comparison_methodology must be consistent with amount_kind
-- everywhere it appears.

-- (a) The exact-context key must be 1:1 with its methodology: one
-- service_context_key can never span two comparison_methodology values.
select service_context_key
from {{ ref('gld_int__service_comparison_spine') }}
group by service_context_key
having count(distinct comparison_methodology) > 1

union all

-- (b) Ranking rows: negotiated dollars carry a rankable methodology; every
-- other amount kind is 'not applicable'.
select service_context_key
from {{ ref('gld_mart__service_price_comparison_current') }}
where is_price_ranking_row = true
    and (
        (
            amount_kind = 'negotiated_dollar'
            and comparison_methodology not in
                ('fee schedule', 'case rate', 'per diem')
        )
        or (
            amount_kind <> 'negotiated_dollar'
            and comparison_methodology <> 'not applicable'
        )
    )

union all

-- (c) Hospital representatives: gross/cash contexts are 'not applicable';
-- negotiated contexts carry exactly the rankable methodologies.
select service_context_key
from {{ ref('gld_int__hospital_service_amounts') }}
where (
        amount_kind = 'negotiated_dollar'
        and comparison_methodology not in
            ('fee schedule', 'case rate', 'per diem')
    )
    or (
        amount_kind in ('gross_charge', 'discounted_cash')
        and comparison_methodology <> 'not applicable'
    )
