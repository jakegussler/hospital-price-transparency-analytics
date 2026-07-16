# 0017: Define The v1 Gold Comparability Framework

Status: accepted (comparison key and market-statistic weighting amended by
decision 0021)

## Context

Silver Core now exposes the identity and context fields Gold needs to make
cross-hospital comparison decisions explicitly:

- billing-code match keys, format status, cross-hospital comparability, and
  specificity flags in `slv_core__charge_item_codes`;
- within-hospital `service_item_id` and item/drug signatures in
  `slv_core__charge_items`;
- payer identity, payer context, amount semantics, setting, billing class, and
  modifier signature in `slv_core__payer_rates`;
- drug unit context in `slv_core__drug_information` and
  `slv_core__charge_items`;
- readiness metrics in `slv_audit__gold_readiness_gates`.

The recent Gold-readiness audit model is the Silver readiness scorecard. This
decision does not replace it. Instead, it records the row-level comparability
rules Gold must apply when building `gld_fct__rate_observations` and the first
current comparison mart.

The main risk is false precision. HPT rows can share a description while
representing different economic objects, and they can share a code while
differing by setting, billing class, modifier, drug unit, amount semantics,
payer identity, or market segment. Gold should expose those constraints rather
than burying them inside undocumented `where` clauses.

## Decision

Gold v1 compares across hospitals by **code cohort plus context**. It does not
create a cross-hospital service master.

### Comparison Key

Cross-hospital comparison uses (amended by decision 0021, which added
`amount_kind` and `comparison_methodology`):

```text
canonical_code_system
+ match_code
+ clean_setting
+ clean_billing_class
+ modifier_signature
+ amount_kind
+ comparison_methodology (negotiated-rate methodology; 'not applicable'
  for non-negotiated amount kinds)
+ drug unit context when the item is drug/NDC-relevant
```

Phase 1 comparable rows require `code_cross_hospital_comparable = true`.
Price-ranking marts additionally require `code_is_specific = true` and a
non-null `match_code`.

Descriptions, `service_item_id`, and any future within-hospital item identity
are not cross-hospital comparison keys. `service_item_id` remains a
within-hospital identity and lineage aid. Gold v1 will not build a global
`service_group_id`, canonical service master, or fuzzy description-based
service identity.

Multi-code charge items expand into one comparison row per eligible code. Each
expanded row must retain lineage back to the source charge item, standard
charge, payer rate when applicable, and the contributing code row.

### Amount Semantics

Price-ranking marts use dollar amounts only. Percentage and algorithm rows stay
visible in Gold coverage and observation outputs, but they are not rankable as
prices.

`amount_comparability_tier = 'derived_dollar'` rows also stay visible, with
their `methodology`, `amount_comparability_tier`, and raw percentage or
algorithm context. They are not treated as direct negotiated prices and must not
feed direct price rankings unless a future model explicitly publishes a derived
dollar analysis.

Gold should consume Silver Core's `methodology`, `amount_kind`,
`amount_comparability_tier`, and `is_price_comparable` fields. It should not
re-derive payer-rate amount semantics in mart SQL.

### Modifiers And Drug Context

`modifier_signature` is part of the comparison context. Gold must not aggregate
across differing modifier signatures, and must never combine professional and
technical component rows such as modifiers `26` and `TC` as if they were the
same price.

Drug/NDC comparisons must carry drug unit context. Gold v1 does not perform
cross-unit drug quantity conversion.

### Payer, Segment, Plan, And Currentness

Payer-specific benchmarks require `canonical_payer_id`. Rows without a
canonical payer identity can appear in coverage, readiness, and mapping
scorecards, but not in payer benchmark calculations.

Market-segment cuts require `market_segment <> 'unknown'`. Unknown segment rows
remain visible in coverage scorecards and broad observations.

Plan fields are enrichment only. Gold v1 does not require a canonical plan
dimension, and `raw_plan_name`, `clean_plan_name`, `display_plan_name`, and
`plan_type` must not gate inclusion in current comparison marts.

Current comparison marts require `is_current_snapshot = true`.

### Denominators And Summary Metrics

Published percentile and ranking summaries require at least three distinct
hospitals in the exact comparison context. If denominators are thinner than
that threshold, Gold should publish the observation spine and coverage
scorecards first, then delay percentile-heavy marts.

Decision 0021 tightened both sides of this rule: market percentiles are
computed over one representative amount per hospital (never over raw
observations), and the three-hospital floor counts hospitals with a valid
representative amount, not merely hospitals with raw rows.

### Blocker Reasons

Every exclusion from a stricter Gold use case must be explainable as a blocker
reason instead of hidden in a `where` clause. Gold v1 row-level outputs should
expose blocker codes sufficient for scorecards and debugging, including at
minimum:

- `not_current_snapshot`
- `code_not_cross_hospital_comparable`
- `code_not_specific`
- `missing_match_code`
- `non_rankable_amount`
- `derived_dollar`
- `modifier_context_required`
- `drug_unit_context_missing`
- `payer_unmatched`
- `market_segment_unknown`
- `below_min_hospital_denominator`
- `multiple_amounts_per_contract_context` (added by decision 0021)

The blocker list may grow as Gold models are implemented, but new blocker codes
must remain stable, documented values rather than ad hoc text.

These blockers are realized at two grains. The first ten are atomic row-grain
flags emitted by `hpt_comparison_blocker_flags()` and counted per snapshot in
`gld_score__snapshot_coverage_scorecard` / `gld_bi__comparison_blocker_summary`.
`below_min_hospital_denominator` is a service-context cohort (window) property
that cannot be evaluated per row; it is computed where the peer-hospital count is
known (`gld_mart__service_price_summary` / `gld_mart__service_price_comparison_current`)
and surfaced in the BI layer as
`gld_bi__service_market_explorer.comparison_status = 'insufficient_denominator'`.

## Explicit v1 Non-Goals

Gold v1 will not build:

- a global service group or canonical service dimension;
- a canonical plan dimension;
- CBSA or other geography enrichment beyond existing hospital geography;
- a service basket index;
- price history or snapshot-to-snapshot change marts;
- a semantic layer or metrics catalog.

These are additive future capabilities. Price history is specifically scoped as
an extension point by decision 0016.

## Consequences

- `gld_fct__rate_observations` becomes the shared place where amount
  observations, code expansion, comparison context, lineage, and blocker
  reasons are exposed.
- The first current comparison mart can filter to current, dollar-rankable,
  code-specific, context-aligned rows without re-litigating the rules in SQL.
- Coverage scorecards can count blocked rows by reason, including unmatched
  payers, unknown market segments, non-rankable amounts, local codes, missing
  match codes, and thin denominators.
- Silver readiness remains measured by `slv_audit__gold_readiness_gates`.
  Before implementing Gold SQL, rebuild/profile scoped snapshots so the new
  Silver amount-semantics fields are populated across more than the one local
  snapshot currently rebuilt.
- If denominator profiling remains thin after proper rebuilds, build the Gold
  spine and coverage scorecard first and postpone percentile-heavy marts.
