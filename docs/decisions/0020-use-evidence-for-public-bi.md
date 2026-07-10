# 0020: Use Evidence.dev For Public BI

Date: 2026-06-29
Amended: 2026-07-07 (see Amendments)

## Status

Accepted

## Context

HPT needs a public presentation layer for Gold BI marts that explains
comparability limits, denominator floors, trust bands, blocker reasons, snapshot
freshness, and corpus-bounded claims. The presentation layer should not become a
second semantic modeling layer; Python owns ingest, dbt owns normalization and
analytics semantics, and BI tools consume documented Gold BI contracts.

## Decision

Use Evidence.dev as the v1 public dashboard/reporting layer under
`apps/evidence/`. Evidence reads only exported Parquet artifacts generated from
the allowlisted `main_gold.gld_bi__*` marts (nine as of the 2026-07-07
amendment):

- `gld_bi__hospital_overview`
- `gld_bi__service_market_explorer`
- `gld_bi__hospital_service_rankings`
- `gld_bi__payer_contracting_explorer`
- `gld_bi__comparison_blocker_summary`
- `gld_bi__featured_services`
- `gld_bi__market_summary`
- `gld_bi__comparability_funnel`
- `gld_bi__payer_overview`

The public app queries only `hpt.<source_name>` tables created from those
Parquet files. It must not query the working DuckDB warehouse, Silver/Bronze
layers, validation tables, Gold fact tables, or the rate-observation code bridge.

Keep Streamlit as an optional future internal analyst workbench over the same BI
contracts, not the default public surface.

## Consequences

- Public deployment can use a static Evidence build after dbt and artifact
  export.
- DuckDB engine version skew is avoided because Evidence reads Parquet instead
  of a `.duckdb` database file.
- The exporter is the only presentation-layer code that reads
  `main_gold.gld_bi__*` from the working warehouse.
- Evidence SQL guard tests fail if executable source/page SQL references
  disallowed schemas or fact-level tables.
- Any missing comparability, payer matching, amount-kind, or denominator logic
  must be added to dbt before it appears in Evidence.

## Amendments

2026-07-07 — public reporting redesign (phases 1–3 of the Evidence improvement
plan):

- Allowlist expanded from six to nine marts: added `gld_bi__market_summary`
  (one-row corpus KPIs with distinct-count semantics),
  `gld_bi__comparability_funnel` (published→comparable row funnel per
  hospital/corpus), and `gld_bi__payer_overview` (per-payer aggregates). All
  aggregation stays in dbt; Evidence page SQL still only filters, sorts, and
  formats.
- The exporter also generates two documented artifacts alongside the marts:
  `public_metadata` (now including a `build_id` git identifier and the
  download-bundle CSV file names) and `public_data_dictionary` (parsed from
  `_gold_bi_models.yml` column descriptions, which are therefore public
  documentation).
- The exporter writes a public download bundle (Parquet + CSV per mart, the
  dictionary, and a generated README) into `apps/evidence/static/downloads/`;
  CSVs over 25 MB ship gzip-compressed.
- `trust_band` was split into `data_confidence_band` (hospital) and
  `comparison_confidence_band` (service context) because one public name for
  two different measures was an artifact-level ambiguity.
- Public service URLs use the new `service_url_slug` field instead of the md5
  `service_code_key`.

