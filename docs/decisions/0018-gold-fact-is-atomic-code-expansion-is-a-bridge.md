# 0018: Gold Rate Fact Is Atomic; Code Expansion Is A Bridge

Status: accepted

## Context

Decision [0017](0017-gold-comparability-framework.md) defines the v1 Gold
comparability framework and, in its Consequences, describes
`gld_fct__rate_observations` as the single place that exposes "amount
observations, code expansion, comparison context, lineage, and blocker reasons."

Implementing that literally has a structural problem. A charge item can carry
several billing codes (a CPT *and* an NDC, multiple local codes). Profiling the
reduced local corpus shows an average of **1.59 comparable code cohorts per
observation** (max 3; 59% of observations fan out to more than one). If the rate
fact itself expands "one row per eligible code," then a single `$100` gross
charge with two codes becomes two `$100` rows, `sum(amount_value)` double counts,
and every downstream consumer must remember to `count(distinct observation)`. The
fact stops being additive — a Kimball anti-pattern.

## Decision

Split 0017's single "expanded spine" into two models:

1. **`gld_fct__rate_observations` is the atomic fact.** Grain: one row per
   `(source charge/rate row, amount_kind)`. It does **not** fan out on billing
   code. It is the additive, reconcilable source of truth for "how many dollars
   were reported."
2. **`gld_bridge__rate_observation_code` is a bridge.** Grain: one row per
   `(observation, billing code)`. It carries the many-to-many code expansion and
   exposes (never filters) the comparability flags.

The code-expanded, blocker-annotated surface that 0017 asks for is materialized
**downstream** by `gld_mart__service_price_comparison_current` (`fact ⋈ bridge ⋈
dims`), with the atomic fact underneath guaranteeing no double count. The
intermediate `gld_int__service_comparison_spine` persists the semantically
equivalent observation × service-cohort expansion once so the mart's several
peer cuts read it back instead of rebuilding it. For memory efficiency it
deduplicates service cohorts from `slv_core__charge_item_codes` at charge-item
grain before joining them to amount observations; performing the same `distinct`
after the observation-level bridge fan-out creates an unnecessarily large
blocking aggregate. The lineage-preserving bridge remains the authoritative
observation-to-source-code relation.

All of 0017's *rules* are implemented verbatim: the code-cohort + context
comparison key, `code_cross_hospital_comparable` / `code_is_specific` gates,
dollar-only ranking via the Silver amount-semantics fields, `modifier_signature`
with the 26/TC guard, payer/segment gating with plan-never-gates,
`is_current_snapshot` currentness, the 3-hospital denominator, and the stable
blocker-code vocabulary. Only the *arrangement* changed.

## Consequences

- The fact is additive: `sum(amount_value)` and `count(*)` are correct without
  de-duplication, and the snapshot coverage scorecard reconciles to it by
  construction.
- Code expansion is opt-in: consumers that need cross-hospital comparison join
  through the bridge; consumers that need "how much was reported" read the fact
  directly.
- The bridge exposes non-comparable and null-keyed codes (with a null
  `service_code_key`) so the coverage scorecard can count what is published at
  all, not only what compares.
- This is a documented refinement of 0017's wording, not a change to its rules.
  0017 remains accepted and authoritative for the framework; this record governs
  the fact/bridge split.
