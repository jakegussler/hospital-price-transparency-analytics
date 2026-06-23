-- Gold-readiness scorecard for the Silver identity and semantics contracts.
-- This is an observability surface, not a filter and not a hard-failing dbt
-- gate: Gold consumers should expose trust/blocker context instead of dropping
-- imperfect Silver rows.
with current_snapshots as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
    where is_current_snapshot = true
),

current_payer_rates as (
    select pr.*
    from {{ ref('slv_core__payer_rates') }} pr
    inner join current_snapshots
        on pr.snapshot_id = current_snapshots.snapshot_id
),

current_charge_items as (
    select charge_items.*
    from {{ ref('slv_core__charge_items') }} charge_items
    inner join current_snapshots
        on charge_items.snapshot_id = current_snapshots.snapshot_id
),

current_charge_item_codes as (
    select codes.*
    from {{ ref('slv_core__charge_item_codes') }} codes
    inner join current_snapshots
        on codes.snapshot_id = current_snapshots.snapshot_id
),

unmatched_payer_candidates as (
    select
        coalesce(clean_payer_name, '<missing_payer_name>') as clean_payer_name,
        count(*) as payer_rate_rows
    from current_payer_rates
    where canonical_payer_id is null
    group by coalesce(clean_payer_name, '<missing_payer_name>')
),

service_item_hospital_scope_violations as (
    select
        service_item_id,
        count(distinct hospital_id) as hospital_count
    from current_charge_items
    where service_item_id is not null
    group by service_item_id
    having count(distinct hospital_id) > 1
),

metrics as (
    select
        count(*) as payer_rate_rows,
        count(*) filter (where canonical_payer_id is not null) as payer_identified_rows,
        count(*) filter (where market_segment <> 'unknown') as market_segment_resolved_rows,
        count(*) filter (where plan_type is not null) as plan_type_populated_rows,
        count(*) filter (
            where methodology is null
                or methodology_basis is null
                or amount_kind is null
                or amount_comparability_tier is null
                or is_price_comparable is null
        ) as amount_semantics_missing_rows
    from current_payer_rates
),

unmatched_metrics as (
    select
        coalesce(sum(payer_rate_rows), 0) as unmatched_payer_rate_rows,
        coalesce(max(payer_rate_rows), 0) as max_unmatched_candidate_rows,
        count(*) filter (where payer_rate_rows > 100000) as over_threshold_candidate_count
    from unmatched_payer_candidates
),

code_metrics as (
    select
        count(*) as code_rows,
        count(*) filter (
            where code_format_status is null
                or code_cross_hospital_comparable is null
                or code_is_specific is null
        ) as code_contract_missing_rows,
        count(*) filter (
            where code_format_status in (
                'invalid_format',
                'unknown_code_system',
                'missing_code',
                'missing_code_system'
            )
            or ndc_format_status in (
                'ambiguous_10_unhyphenated',
                'invalid_layout',
                'invalid_length'
            )
        ) as code_finding_rows
    from current_charge_item_codes
),

service_metrics as (
    select
        count(*) as charge_item_rows,
        count(*) filter (where service_item_id is null) as missing_service_item_rows
    from current_charge_items
),

service_scope_metrics as (
    select count(*) as service_item_hospital_scope_violation_count
    from service_item_hospital_scope_violations
)

select
    'payer_identity_coverage' as gate_name,
    'pct_payer_rate_rows_with_canonical_payer_id' as metric_name,
    round(
        100.0 * payer_identified_rows / nullif(payer_rate_rows, 0),
        2
    ) as metric_value,
    97.0 as threshold_value,
    case
        when payer_rate_rows = 0 then 'fail'
        when 100.0 * payer_identified_rows / payer_rate_rows >= 97.0 then 'pass'
        else 'fail'
    end as gate_status,
    payer_identified_rows as numerator_count,
    payer_rate_rows as denominator_count,
    payer_rate_rows - payer_identified_rows as blocker_count,
    'Canonical payer identity should cover at least 97% of current payer-rate rows.' as notes
from metrics

union all

select
    'unmatched_payer_backlog' as gate_name,
    'max_unmatched_payer_candidate_rows' as metric_name,
    max_unmatched_candidate_rows::double as metric_value,
    100000.0 as threshold_value,
    case
        when max_unmatched_candidate_rows <= 100000 then 'pass'
        else 'fail'
    end as gate_status,
    max_unmatched_candidate_rows as numerator_count,
    unmatched_payer_rate_rows as denominator_count,
    over_threshold_candidate_count as blocker_count,
    'Largest unreviewed unmatched payer candidate must not exceed 100k current payer-rate rows.' as notes
from unmatched_metrics

union all

select
    'market_segment_coverage' as gate_name,
    'pct_payer_rate_rows_with_known_market_segment' as metric_name,
    round(
        100.0 * market_segment_resolved_rows / nullif(payer_rate_rows, 0),
        2
    ) as metric_value,
    85.0 as threshold_value,
    case
        when payer_rate_rows = 0 then 'fail'
        when 100.0 * market_segment_resolved_rows / payer_rate_rows >= 85.0 then 'pass'
        else 'fail'
    end as gate_status,
    market_segment_resolved_rows as numerator_count,
    payer_rate_rows as denominator_count,
    payer_rate_rows - market_segment_resolved_rows as blocker_count,
    'Market segment should be known for at least 85% of current payer-rate rows.' as notes
from metrics

union all

select
    'plan_type_coverage' as gate_name,
    'pct_payer_rate_rows_with_plan_type' as metric_name,
    round(
        100.0 * plan_type_populated_rows / nullif(payer_rate_rows, 0),
        2
    ) as metric_value,
    null::double as threshold_value,
    'info' as gate_status,
    plan_type_populated_rows as numerator_count,
    payer_rate_rows as denominator_count,
    payer_rate_rows - plan_type_populated_rows as blocker_count,
    'Informational only: low plan_type coverage is expected and does not block Gold.' as notes
from metrics

union all

select
    'code_normalization_contract' as gate_name,
    'missing_code_status_or_comparability_rows' as metric_name,
    code_contract_missing_rows::double as metric_value,
    0.0 as threshold_value,
    case
        when code_contract_missing_rows = 0 then 'pass'
        else 'fail'
    end as gate_status,
    code_rows - code_contract_missing_rows as numerator_count,
    code_rows as denominator_count,
    code_contract_missing_rows as blocker_count,
    'Requires populated code status/comparability fields; code finding rows='
        || code_finding_rows::varchar
        || ' are audit findings, not automatic blockers.' as notes
from code_metrics

union all

select
    'service_identity_contract' as gate_name,
    'missing_service_item_or_hospital_scope_rows' as metric_name,
    (
        missing_service_item_rows
        + service_item_hospital_scope_violation_count
    )::double as metric_value,
    0.0 as threshold_value,
    case
        when missing_service_item_rows = 0
            and service_item_hospital_scope_violation_count = 0
            then 'pass'
        else 'fail'
    end as gate_status,
    charge_item_rows - missing_service_item_rows as numerator_count,
    charge_item_rows as denominator_count,
    missing_service_item_rows + service_item_hospital_scope_violation_count as blocker_count,
    'Requires non-null service_item_id and no service_item_id spanning multiple hospitals; hospital-scope violations='
        || service_item_hospital_scope_violation_count::varchar
        || '.' as notes
from service_metrics
cross join service_scope_metrics

union all

select
    'amount_semantics_contract' as gate_name,
    'missing_methodology_or_amount_semantics_rows' as metric_name,
    amount_semantics_missing_rows::double as metric_value,
    0.0 as threshold_value,
    case
        when amount_semantics_missing_rows = 0 then 'pass'
        else 'fail'
    end as gate_status,
    payer_rate_rows - amount_semantics_missing_rows as numerator_count,
    payer_rate_rows as denominator_count,
    amount_semantics_missing_rows as blocker_count,
    'Requires methodology, methodology_basis, amount_kind, amount_comparability_tier, and is_price_comparable to be populated after rebuild.' as notes
from metrics
