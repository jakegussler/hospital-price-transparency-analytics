-- Cash-compatibility guards (decision 0021): a per-diem rate is a DAILY payment
-- and must never be labeled above/below a cash amount; ambiguous contexts must
-- stay visible with null statistics; the status enum must match the fields.
select *
from {{ ref('gld_mart__payer_service_benchmarks') }}
where
    -- per-diem rows never publish cash deltas and never read 'comparable'
    (
        comparison_methodology = 'per diem'
        and (
            delta_from_hospital_cash is not null
            or pct_delta_from_hospital_cash is not null
            or cash_comparison_status = 'comparable'
        )
    )
    -- ambiguous rows: no representative, no deltas, no market stats
    or (
        cash_comparison_status = 'ambiguous_negotiated_context'
        and (
            negotiated_dollar is not null
            or delta_from_hospital_cash is not null
            or payer_market_median_negotiated is not null
            or delta_from_payer_market_median is not null
        )
    )
    -- a null representative must always be labeled ambiguous
    or (
        negotiated_dollar is null
        and cash_comparison_status <> 'ambiguous_negotiated_context'
    )
    -- 'comparable' requires an actual cash amount
    or (cash_comparison_status = 'comparable' and hospital_cash_amount is null)
    -- deltas only on 'comparable' rows
    or (
        cash_comparison_status <> 'comparable'
        and delta_from_hospital_cash is not null
    )
