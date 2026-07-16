-- Ambiguity rules (decision 0021): a contract/context with exactly one distinct
-- amount MUST carry it as the representative; a multi-amount contract/context
-- MUST carry none (flagged, excluded, never silently averaged). The
-- representative, when present, must equal both bounds.
select *
from {{ ref('gld_int__service_contract_representatives') }}
where (distinct_amount_count = 1 and contract_representative_amount is null)
    or (distinct_amount_count > 1 and contract_representative_amount is not null)
    or (has_multiple_contract_amounts <> (distinct_amount_count > 1))
    or (
        contract_representative_amount is not null
        and (
            contract_representative_amount <> contract_amount_min
            or contract_representative_amount <> contract_amount_max
        )
    )
