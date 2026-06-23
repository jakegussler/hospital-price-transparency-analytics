-- Duplicate payer/plan context findings for Silver Core payer rates. One row
-- per comparable rate unit (the analytic business grain: item + setting +
-- billing class + canonical payer + plan + methodology + modifier signature +
-- amount_kind) that appears more than once within a snapshot. This is the
-- duplicate-context signal called out in the productionize plan (item 4): the
-- positional silver_payer_rate_id stays unique, so genuine business-grain
-- repeats only surface here, not in a uniqueness test.
--
-- Two flavors are distinguished by the distinct-amount counts:
--   * has_conflicting_amounts = false -> redundant rows (same context AND amount)
--   * has_conflicting_amounts = true  -> conflicting rates for one context
--     (same payer/plan/context, different negotiated value) -- the sharper
--     data-quality concern.
--
-- Findings for humans to read; item identity and rate semantics are algorithmic,
-- so there is no accept/reject workflow. Scoped to current snapshots so
-- superseded snapshots do not double-count under all_snapshots retention.
with current_snapshots as (
    select snapshot_id
    from {{ ref('slv_base__hospital_snapshots') }}
    where is_current_snapshot = true
),

scoped_rates as (
    select pr.*
    from {{ ref('slv_core__payer_rates') }} pr
    inner join current_snapshots
        on pr.snapshot_id = current_snapshots.snapshot_id
),

grouped as (
    select
        snapshot_id,
        hospital_id,
        silver_charge_item_id,
        clean_setting,
        clean_billing_class,
        canonical_payer_id,
        clean_plan_name,
        methodology,
        modifier_signature,
        amount_kind,
        count(*) as duplicate_row_count,
        count(distinct negotiated_dollar) as distinct_dollar_count,
        count(distinct negotiated_percentage) as distinct_percentage_count,
        count(distinct {{ hpt_clean_display_text('negotiated_algorithm') }}) as distinct_algorithm_count,
        min(silver_payer_rate_id) as example_silver_payer_rate_id,
        min(clean_payer_name) as example_clean_payer_name
    from scoped_rates
    group by
        snapshot_id,
        hospital_id,
        silver_charge_item_id,
        clean_setting,
        clean_billing_class,
        canonical_payer_id,
        clean_plan_name,
        methodology,
        modifier_signature,
        amount_kind
)

select
    *,
    (
        distinct_dollar_count > 1
        or distinct_percentage_count > 1
        or distinct_algorithm_count > 1
    ) as has_conflicting_amounts
from grouped
where duplicate_row_count > 1
order by duplicate_row_count desc, hospital_id, snapshot_id
