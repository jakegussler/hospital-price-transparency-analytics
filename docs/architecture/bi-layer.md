# BI Presentation Layer

The BI layer is prepared in dbt before any dashboard tool is configured. Its
purpose is to give Evidence, Streamlit, Power BI, Metabase, or a future hosted
serving target boring, wide, documented tables that already encode Gold's
comparability and trust rules.

## Naming

Use `gld_bi__*` for dashboard-ready presentation marts. This name is deliberate:
the models are broader than a portfolio-only publication export, but they are not
the atomic fact, bridge, or core analytical marts. They are the default BI
surface.

## Models

- `gld_bi__hospital_overview` — one row per hospital/current scored snapshot.
- `gld_bi__service_market_explorer` — one row per exact comparison context
  (`service_context_key`: service, setting, billing class, modifiers, amount
  kind, comparison methodology, drug unit context). All statistics are
  hospital-weighted and methodology-separated (decision 0021).
- `gld_bi__hospital_service_rankings` — one row per hospital and exact
  comparison context.
- `gld_bi__payer_contracting_explorer` — one row per payer/hospital/exact
  comparison context, with `cash_comparison_status` methodology guards.
- `gld_bi__comparison_blocker_summary` — one row per snapshot/blocker code.
- `gld_bi__featured_services` — rule-selected dashboard defaults from the
  service explorer.
- `gld_bi__market_summary` — exactly one corpus-level row with distinct-count
  headline KPIs, so dashboards never sum per-hospital counts (which would
  double-count services and payers shared across hospitals).
- `gld_bi__comparability_funnel` — one row per scope (`hospital` or `corpus`
  with the `<corpus>` sentinel), hospital, and funnel stage: classified price
  rows surviving each cumulative decision-0017 gate. Stage monotonicity is
  locked by `gld_bi_funnel_stage_monotonic.sql`.
- `gld_bi__payer_overview` — one row per matched canonical payer with
  distinct-count aggregates and cash-comparison band counts.

## Rules

- Keep comparability, denominator floors, payer matching, and blocker logic in
  Gold/dbt, not in the BI tool.
- Preserve technical keys (`hospital_id`, `snapshot_id`, `service_code_key`,
  `canonical_payer_id`, `modifier_signature`) beside display labels for
  drill-down.
- Treat readiness scores as published-data usability measures, not legal
  compliance.
- Use `gld_bi__featured_services` as a starter list only; do not treat it as a
  canonical service master.
- **Column descriptions in `_gold_bi_models.yml` are public documentation.**
  The Evidence artifact exporter parses that yml into the published
  `public_data_dictionary` artifact, so every selected column must be listed
  with a plain-language description a public data user can follow.

## Confidence Bands Are Two Different Measures

The former shared `trust_band` name was a public-artifact ambiguity and was
split (2026-07-07):

- `gld_bi__hospital_overview.data_confidence_band` — how usable the hospital's
  published file is, banded from `overall_readiness_score` (high ≥ 0.85 /
  moderate ≥ 0.70 / limited ≥ 0.50 / low).
- `gld_bi__service_market_explorer.comparison_confidence_band` (also carried by
  `gld_bi__featured_services`) — how solid a service context's cross-hospital
  comparison is (high = 10+ hospitals and described / moderate = 5+ / limited =
  meets the 3-hospital floor / low = below the floor).

Both use the values `high`/`moderate`/`limited`/`low`, locked by
accepted-values tests. Do not reintroduce a bare `trust_band` column in any
public mart.

## Presentation Helper Fields

- `service_url_slug` (`hpt_service_url_slug` macro in
  `transform/macros/bi_presentation.sql`) — URL-safe service identifier
  (for example, `ms-drg-470`) derived from `(canonical_code_system,
  match_code)`; it is 1:1 with `service_code_key`, locked by
  `gld_bi_service_slug_one_to_one.sql`. Public service page routes use it
  instead of the MD5 `service_code_key`.
- `service_context_url_slug` (`hpt_service_context_url_slug` macro) — URL-safe
  exact-context identifier (for example,
  `ms-drg-003-negotiated-per-diem-3f2a9c1d2e`): the service slug, the public
  price-type word, the methodology when applicable, and a 10-char prefix of
  `service_context_key`. 1:1 with `service_context_key`, locked by
  `gld_bi_context_slug_one_to_one.sql`. This is the durable cross-page link
  target — hospital, payer, and featured-service links must carry it so the
  exact methodology-specific context is never lost in navigation (decision
  0021).
- `comparison_methodology_display_label`
  (`hpt_comparison_methodology_display_label` macro) — spells out the payment
  unit: 'Fee schedule (per item/service)', 'Case rate (per episode)',
  'Per diem (per day)', 'Not applicable'.
- `description_availability` (`hpt_description_availability` macro) — why a
  code description is or is not shown: `available`, `license_restricted`
  (CPT/CDT descriptions cannot be republished; not a hospital failure), or
  `not_loaded` (public-domain reference data not yet loaded). The display-name
  fallback is `Description not available`, never `Undescribed service`.

## Blocker Vocabulary Spans Marts By Grain

Decisions 0017 and 0021 name 12 blocker codes. They are split across BI
surfaces because they live at different grains, and any UI that lists blocker
vocabulary must read all of them:

- The 10 atomic row-grain blockers (`not_current_snapshot`,
  `code_not_cross_hospital_comparable`, `code_not_specific`,
  `missing_match_code`, `non_rankable_amount`, `derived_dollar`,
  `modifier_context_required`, `drug_unit_context_missing`, `payer_unmatched`,
  `market_segment_unknown`) are published per snapshot/blocker code in
  `gld_bi__comparison_blocker_summary`.
- `below_min_hospital_denominator` is a service-context cohort property
  (fewer than 3 hospitals with a valid representative) that cannot be
  evaluated per atomic row. It is surfaced as
  `gld_bi__service_market_explorer.comparison_status =
  'insufficient_denominator'`, not as a row in the blocker summary.
  `gld_bi__comparability_funnel` stage 5 applies the same gate corpus- and
  hospital-wide.
- `multiple_amounts_per_contract_context` (decision 0021) is a contract-grain
  property (one source contract carrying multiple distinct amounts for one
  exact context). It is surfaced as a boolean/blocker-reason on
  `gld_mart__service_price_comparison_current` rows and aggregated as the
  explorer's `ambiguous_contract_count` / `excluded_hospital_count` and the
  payer explorer's `cash_comparison_status = 'ambiguous_negotiated_context'`.

This split is intentional (see the `hpt_comparison_blocker_flags` macro and the
`gld_score__snapshot_coverage_scorecard` headers). The contract is locked by the
`blocker_code` accepted values and the singular test
`gld_bi_denominator_blocker_surfaced.sql`. Service and diagnostics pages must
surface `comparison_status` prominently so thin cohorts are visibly labeled,
never silently dropped.

## Build

Use the project wrapper, never direct `dbt`:

```bash
hpt run-dbt --command build --selector gold_bi
hpt run-dbt --command test --selector gold_bi
```

When rebuilding the full Gold layer after a per-snapshot corpus refresh, build
the selectors in dependency order:

```bash
hpt run-dbt --per-snapshot --full-refresh --selector gold_dimension,gold_per_snapshot
hpt run-dbt --command build --selector gold_marts,gold_scorecards,gold_bi
```

For day-to-day edits, prefer focused node selection:

```bash
hpt run-dbt --command build --select gld_bi__hospital_overview+
```
