# 0015: Classify Methodology And Amount Semantics In Silver Core

Status: accepted

## Context

Gold rate comparisons need to know what a payer-rate value actually represents.
`slv_base__payer_rates.clean_methodology` preserves a cleaned source string, but
it did not provide an enforced taxonomy or a reusable signal for whether a row's
dollar value is directly comparable. Hospitals also sometimes publish a
pre-computed `standard_charge_dollar` even when the underlying contract is a
percentage of billed charges or a compound `other` algorithm. Those values are
useful, but they are not the same as a fee-schedule dollar.

CMS v3 count strings also carry reliability context for percentage and algorithm
rates. Silver Base preserved `raw_count`, but Core did not expose parsed bounds.

## Decision

`slv_core__payer_rates` is the source of truth for payer-rate methodology and
amount semantics. It adds:

- `methodology`: one of the CMS display values (`case rate`, `fee schedule`,
  `percent of total billed charges`, `per diem`, `other`) or `unmapped`.
- `methodology_basis`: `cms_value`, `mapped`, or `unmapped`; `mapped` is
  reserved for a future alias map and is not emitted initially.
- `amount_kind`: `dollar`, `percentage`, `algorithm`, `estimated`, or `none`,
  resolved by priority in that order.
- `amount_comparability_tier`: `comparable_dollar`, `derived_dollar`,
  `percentage`, `algorithm`, or `none`.
- `is_price_comparable`: true exactly when the tier is `comparable_dollar`.
- `count_raw`, `count_min`, and `count_max`: public count string plus parsed
  bounds for CMS-valid count formats.

The methodology column intentionally uses CMS display strings rather than the
older planning-playbook snake_case names. That keeps Silver Core aligned with
the source specification and avoids inventing a second public enum.

Dollar comparability is methodology-aware:

- `fee schedule`, `case rate`, and `per diem` dollar rows are
  `comparable_dollar`.
- `percent of total billed charges`, `other`, and `unmapped` dollar rows are
  `derived_dollar`.
- A dollar value is preserved as published. It is never nulled solely because
  the methodology means it was pre-computed.
- Percentage-only and algorithm-only rows remain typed as non-dollar values.
- `estimated_amount` is an amount kind, but it is not a comparable negotiated
  price. v3 allowed-amount percentile fields do not become the authoritative
  amount kind.

Shared dbt macros own the CMS methodology value set and count parsing so Core
classification and validation cannot drift.

## Consequences

- Gold can default to `is_price_comparable` for price-ranking use cases while
  still allowing explicit analysis of derived dollars, percentages, algorithms,
  and estimates.
- The validation layer still excludes invalid methodology rows before Silver
  when the CMS rule applies; `unmapped` is primarily a defensive and unit-tested
  fallback for future alias or source changes.
- No methodology alias seed is introduced yet. If alias mapping is added later,
  it must emit `methodology_basis = 'mapped'` and keep the same public enum.
- Older planning language that proposed `canonical_methodology` and
  `dollar_basis` is superseded by `methodology` and
  `amount_comparability_tier`.
