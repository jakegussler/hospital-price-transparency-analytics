# 0021: Separate Methodology And Weight Hospitals Equally In Market Statistics

Status: accepted

## Context

The first public build exposed a misleading market statistic. For MS-DRG 003
(and roughly 87% of comparable MS-DRG contexts on the profiled corpus), the
published "bottom 10% hospital price" was $1,947. That value is an authentic
published rate — one hospital's United/VACCN **per diem**, repeated across 56
revenue-code variants of the same MS-DRG — but it was presented as the lower
end of an episode-price distribution whose other members were case rates near
$155,000.

Two modeling choices caused this:

1. `gld_mart__service_price_summary` computed percentiles over **every**
   price-ranking observation. Repeated contract rows and revenue-code variants
   received one statistical vote each, so a single hospital repeating one rate
   56 times outweighed ten hospitals publishing one rate each.
   `gld_mart__service_price_comparison_current` computed its market peer
   statistics the same way, while `gld_mart__hospital_service_benchmarks`
   already aggregated per hospital first — meaning the project published two
   different definitions of the same service P10.
2. The decision 0017 comparison key omitted negotiated-rate methodology, so
   `per diem` daily amounts, `case rate` episode amounts, and `fee schedule`
   item amounts entered the same distribution even though they price different
   economic units.

## Decision

Negotiated-rate methodology is part of the economic unit being compared, and
market statistics are computed hierarchically with one vote per hospital:

```text
Source rate rows (atomic fact, grain unchanged)
    -> collapse exact repetitions; quarantine ambiguous multi-amount contracts
One representative amount per source contract
    -> median of valid contract representatives
One representative amount per hospital
    -> percentiles over hospitals, within exactly one methodology
Market median / P10 / P90
    -> BI marts and Evidence
```

The exact comparison context for market statistics becomes:

```text
service_code_key
+ clean_setting
+ clean_billing_class
+ modifier_signature
+ amount_kind
+ comparison_methodology
+ drug unit context when the item is drug/NDC-relevant
```

Payer-specific cuts additionally include `canonical_payer_id`.

### Rules

- Raw published amounts remain unchanged in Bronze, Silver, and the atomic
  Gold fact. This decision supersedes the market-statistic weighting and
  comparison-key portions of decisions 0015 and 0017; it does not alter their
  source-preservation or amount-classification rules.
- `fee schedule`, `case rate`, and `per diem` remain valid directly published
  dollars (`comparable_dollar` per 0015). Being a valid dollar does not make
  different methodologies mutually comparable.
- No conversion between per-diem and case rates is attempted. A per-diem value
  is a daily payment; it is only compared with other per-diem values.
- `comparison_methodology` is `methodology` for `negotiated_dollar`
  observations and `'not applicable'` for every other amount kind. Negotiated
  dollars from `percent of total billed charges`, `other`, or `unmapped`
  methodologies remain visible in the atomic spine as `derived_dollar` rows
  and never enter representative-price models (unchanged from 0015/0017).
- Every negotiated-price cohort contains exactly one methodology. No market
  statistic may aggregate across differing `comparison_methodology` values.
- Every market distribution weights hospitals equally: one representative
  amount per hospital per exact context. Repeated source rows must not give a
  contract or hospital extra weight.
- Contract identity (`source_contract_key`) is built from the snapshot,
  hospital, cleaned source payer name, cleaned source plan name, and
  methodology. Source labels — not only `canonical_payer_id` — define the
  contract so unmatched insurers are still represented correctly.
  `contract_identity_precision` records how much identity backed the key:
  `payer_plan` (both labels present), `payer_only` (plan label missing; safe
  because multi-amount collapse is quarantined), or `row` (payer label
  missing; the key falls back to a row-specific identity rather than merging
  unrelated rows).
- A contract/context with exactly one distinct amount uses it as the contract
  representative. A contract/context with multiple distinct amounts is flagged
  `multiple_amounts_per_contract_context` and excluded from price ranking
  until the hidden context (often a revenue-code or network distinction) is
  modeled. Ambiguous contexts stay visible; they are blocked from ranking, not
  silently averaged.
- The three-hospital denominator floor counts hospitals with a **valid
  representative amount** (`hospital_count`), not merely hospitals with raw
  rows (`reporting_hospital_count`). Published outputs expose both counts plus
  `excluded_hospital_count` so the denominator definition is visible.
- Payer-to-cash comparisons expose methodology compatibility via
  `cash_comparison_status`. A per-diem rate is never labeled above or below a
  cash amount, because one is a daily payment and the other may describe an
  entire item or episode.

### Empirical basis for the strict ambiguity rule

On the profiled corpus, 94.8% of contract/contexts had exactly one distinct
amount; strict exclusion removed only 5.9% of hospital-method-contexts, and a
relaxed variant (allowing amount variation across different charge items)
recovered fewer than 0.1% more. 87.5% of multi-amount contract/contexts varied
within a single charge item — genuine hidden-context ambiguity. The strict
rule is therefore both safe and simple.

## Consequences

- `gld_fct__rate_observations` gains `clean_payer_name`, `clean_plan_name`,
  `source_contract_key`, and `contract_identity_precision`; its grain is
  unchanged.
- Two materialized intermediates own the representative hierarchy:
  `gld_int__service_contract_representatives` (one row per hospital, snapshot,
  exact context, source contract) and `gld_int__hospital_service_amounts` (one
  row per hospital and exact context). Service summary, hospital benchmarks,
  and payer benchmarks all read the same representatives, so their percentiles
  reconcile by construction.
- The market fields of `gld_mart__service_price_comparison_current`
  (`market_median_amount`, P10/P90, `amount_pct_rank`, deltas) are redefined
  as hospital-weighted rather than kept as legacy observation-weighted
  measures. All ranked rows from one hospital/context share the hospital's
  rank and deltas against its representative amount.
- Context counts increase (a mixed negotiated context can split into up to
  three method-specific contexts) and comparable counts can decrease (some
  method-specific cohorts fall below the three-hospital floor). That is
  expected and more honest.
- Public BI grains gain `comparison_methodology` and a stable
  `service_context_key` / `service_context_url_slug`, which becomes the
  durable cross-page link target in Evidence.
- Public exports carry `analytics_contract_version =
  'hospital_weighted_methodology_v2'` so downloaded datasets identify the
  changed statistic definitions.
