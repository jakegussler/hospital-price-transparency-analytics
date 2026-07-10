# Hospital Price Transparency

Hospital Price Transparency is a local-first data pipeline for working with CMS
hospital machine-readable files (MRFs). It downloads hospital source files,
tracks file snapshots, parses JSON and CSV layouts into source-faithful Bronze
Parquet, and models the data with dbt and DuckDB.

The project is built for research and engineering work on hospital price
transparency data. It emphasizes reproducible snapshots, source lineage, and a
clear separation between structural parsing in Python and semantic modeling in
dbt.

## Project Status

This is an active data engineering project with a working local ingestion and
modeling pipeline. The Python downloader, snapshot tracker, Bronze parsers, dbt
staging models, Silver foundation models, Silver payer normalization models,
review queues, the Gold analytics layer (conformed dimensions, the atomic
rate-observation fact, the code bridge, the current price-comparison and
benchmark marts, and the coverage/transparency scorecards), the nine `gld_bi__*`
presentation marts, and a static public reporting app (Evidence.dev, under
`apps/evidence/`) are implemented.

Orchestration, Docker, and Terraform are not production-ready in this repository
yet.

## Why This Project Matters

Hospital price transparency data is public, valuable, and difficult to use in
practice. Hospitals publish large files in multiple layouts, with inconsistent
headers, nested payer contracts, changing URLs, mixed code systems, and
publisher-specific data quality issues.

This project addresses those problems as a reproducible healthcare analytics
pipeline: it captures source snapshots, preserves lineage, parses multiple MRF
formats, quarantines invalid records, applies quality checks, and builds
analytics-ready Silver models for downstream analysis.

## Findings — Nashville Metro Sample (Illustrative)

The pipeline is built for **national scale**, but running it nationwide is a
breadth-and-infrastructure effort still in progress. To demonstrate the analytical
output the Gold layer produces *today*, the active corpus is deliberately scoped
to a **single comparable market — the Nashville, TN metro** — as a **small-sample
placeholder, not the project's end goal** (decision 0019). Concentrating on one
market is intentional: cross-hospital price comparison only works when hospitals
share code systems and service lines, so a geographic grab-bag maximizes *N* while
minimizing *comparability*.

> **Read these as transparency, comparability, and data-quality findings — not a
> market price study.** Every cross-hospital figure is captioned with its
> denominator; Gold suppresses any cross-hospital statistic whose cohort has fewer
> than three reporting hospitals (the decision 0017 floor). Scores measure
> *published-data readiness, not legal compliance*. The sample is one metro, one
> snapshot per hospital.

### Corpus

**12 active hospitals** — the nine-hospital HCA TriStar division, both Vanderbilt
(VUMC) hospitals, and Metro Nashville General — across JSON and CSV MRF formats.
Two further metro hospitals (Williamson Medical Center, Maury Regional) are
registry entries deactivated for this run: their CSV-wide validation join exceeds
the 8 GiB development machine's memory (a hardware limit, not a data limit — see
`docs/cleanup.md`).

| Metric | Value |
|---|---|
| Hospitals (active) | 12 |
| Charge items | 2.19M |
| Payer rates | 27.7M |
| Atomic rate observations | 43.4M |
| Distinct cross-hospital-comparable code cohorts | 30,054 |

### Published ≠ comparable

- **97.8%** of classified observations are **code-backed** (carry a
  cross-hospital-comparable code).
- **57.2%** are **cross-hospital comparable** (tier 2: code-backed, item-specific,
  context-aligned) — after the one deliberate adjustment below.

**A concrete data-quality finding: none of the 12 hospitals publish
`billing_class`.** The CMS schema defines it (professional vs. facility) and the
parser maps it, but it is absent from every source file in this corpus. The
comparability framework originally required it for context-alignment, so the strict
reading is **0% cross-hospital comparable**. Because the field is *uniformly* absent
(not selectively), this run treats its absence as an explicit `'unspecified'`
context — a documented relaxation of the decision 0017 tier rule (see
`docs/cleanup.md`) — which yields the 57.2% above. Either way the headline is the
same: a field needed for clean apples-to-apples comparison simply is not published.

### How negotiated rates are expressed

Only dollar amounts are directly price-rankable; percentages and contract
algorithms are not. Across 35.3M negotiated observations:

| Expression | Share |
|---|---|
| Negotiated dollar | 78.2% |
| Negotiated algorithm (contract text) | 21.4% |
| Negotiated percentage | 0.4% |

### Per-hospital readiness (coverage, not compliance)

Overall readiness ranges **0.74–0.84** (mean of five 0–1 component scores). Every
hospital publishes high code and amount coverage; they differ most on
**payer-mapping** — HCA TriStar 0.64–0.93, VUMC 1.00, Metro Nashville General 0.57.
VUMC's lower amount-coverage (0.66) reflects fewer dollar-valued cells per rate.

### Code-description legibility (MS-DRG enrichment)

Reference data makes a subset of codes human-readable:

| Code system | Comparable cohorts | Described |
|---|---|---|
| MS-DRG | 791 | **97.7%** (FY2025, public-domain) |
| CPT / HCPCS / CDT / NDC / … | 27,000+ | 0% (licensed or not yet loaded) |

### A few legible example services

With MS-DRG descriptions joined in, here are high-acuity inpatient DRGs reported by
**11 of 12 hospitals** (well above the 3-hospital floor) — each hospital's median
negotiated dollar, then the cross-hospital spread:

| DRG | Service (abbrev.) | Hospitals | Median | P10 | P90 |
|---|---|---|---|---|---|
| 003 | ECMO or tracheostomy, MV >96h | 11 | $159,933 | $155,862 | $303,329 |
| 927 | Extensive / full-thickness burns | 11 | $153,203 | $148,562 | $281,466 |
| 231 | Coronary bypass w/ PTCA + MCC | 11 | $64,960 | $62,791 | $120,219 |
| 020 | Intracranial vascular procedures | 11 | $60,216 | $58,613 | $112,217 |

Even within one metro and a system-heavy cohort, negotiated prices for the same DRG
vary roughly **2× from the 10th to the 90th percentile** across hospitals.

> **Scope honesty.** The atomic fact, code bridge, conformed dimensions, and both
> coverage/transparency scorecards are built over the 12 hospitals. The illustrative
> sample build omits the Phase-2 comparison/benchmark marts (`gld__service_price_*`)
> because their peer-window functions exceed the small-machine temp budget, so the
> figures above are computed directly from the rate-observation fact and the
> coverage scorecard. See `docs/cleanup.md`.

## Current Implementation

The current implementation includes:

- Registry-driven downloads for a curated set of hospital MRF URLs.
- SHA-256 source-file change detection and Type-2 snapshot metadata.
- `fsspec`-backed raw storage, so local files and cloud object stores use the
  same storage abstraction.
- JSON, CSV Tall, and CSV Wide MRF parsing into Bronze Parquet.
- Quarantine output for records that fail parser validation.
- dbt/DuckDB staging views over Bronze Parquet.
- Silver Base models for hospitals, snapshots, locations, NPIs, contract
  provisions, charge items, codes, drug information, standard charges, payer
  rates, modifiers, and modifier-payer information.
- Silver Core payer-rate models with payer alias and payer/plan context matching.
- Incremental dbt materialization for snapshot-grained Silver and validation
  tables, with configurable current-only or all-snapshot retention.
- Review queue models for unmatched payer and payer/plan candidates.
- Gold dimensional models: five conformed dimensions, the atomic
  `gld_fct__rate_observations` fact and `gld_bridge__rate_observation_code`,
  the `gld_mart__service_price_comparison_current` mart with comparability tiers and
  blocker reasons, service/hospital/payer benchmark marts, and snapshot
  coverage + hospital transparency scorecards, plus the nine `gld_bi__*`
  presentation marts for dashboard/report consumption (`main_gold` schema).
- A static public reporting app (Evidence.dev, `apps/evidence/`) that reads only
  exported Parquet from the allowlisted `gld_bi__*` marts and foregrounds
  comparability limits, denominator floors, confidence bands, blocker reasons,
  and snapshot freshness. Comparability logic stays in dbt (decision 0020).
- pytest coverage for configuration, registry validation, download, storage,
  snapshots, parser behavior, Parquet writing, and ingest orchestration.
- Append-only Parquet run audits for download, ingest, and dbt invocations.
- dbt schema and data tests for Bronze sources, staging, Silver, reconciliation,
  and payer normalization rules.
- Grain-aware validation rejection: file/header findings are report-only, while
  entity failures remove only the failing entity and its descendants.

## Repository Map

```text
src/hpt/             Python package and CLI
tests/               pytest suite
transform/           dbt project targeting DuckDB
docs/                Architecture, domain, and development docs
scripts/             Reusable utility scripts
infra/               Placeholder deployment infrastructure
orchestration/       Placeholder Airflow structure
data/                Local runtime output, ignored by git
logs/                Local run logs, ignored by git
```

## Quickstart

Use Python 3.11 or newer and DuckDB 1.5.2 or newer for dbt/DuckDB work.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,warehouse]"
duckdb --version
```

DuckDB 1.5.2 includes fixes required to checkpoint the project's dynamic
`UNPIVOT` staging views. Do not keep an older DuckDB CLI or UI connected to
`data/hpt.duckdb` while dbt is writing to it.

Verify the Python project:

```bash
make test
make lint
hpt --help
```

Download source MRFs from the bundled registry:

```bash
hpt download
```

Parse the current downloaded snapshots into Bronze Parquet:

```bash
hpt ingest
```

Build the DuckDB warehouse with dbt. `hpt run-dbt` is the canonical interface:
it resolves each hospital to its current snapshot, scopes the run, and wraps
`dbt` (do not call `dbt` directly or use materializing `make dbt-*` shortcuts).

```bash
make dbt-deps                                                # install dbt packages (once)
make export-hospitals-seed                                   # active-hospital seed
hpt run-dbt --command build --seeds --hospital-ids vumc      # first build (seed once)
hpt run-dbt --command test --hospital-ids vumc
```

The active corpus (Nashville metro, 14 hospitals) is large enough that a
single-pass 14-hospital build can exhaust DuckDB's temp directory; at
full-corpus scale, build in `--hospital-ids` batches of ~4. See `AGENTS.md`.

By default, raw files, snapshot metadata, Bronze Parquet, quarantine records,
DuckDB files, and logs are written under local ignored paths.

## Common Commands

```bash
# Install
make install-dev

# Python quality checks
make test
make lint
make format

# Pipeline shortcuts
make download
make ingest

# Equivalent CLI commands and option help
hpt download
hpt ingest
hpt download --help
hpt ingest --help
hpt export-hospitals-seed --help
hpt clear-snapshot --help
hpt show-run --run-id <run-uuid>

# dbt — always through hpt run-dbt for dbt execution
hpt run-dbt --command build --seeds --hospital-ids vumc          # first build / seed change
hpt run-dbt --command build --hospital-ids vumc,nashville-general
hpt run-dbt --command build --select slv_core__payer_rates+      # a model and its downstream
hpt run-dbt --command build --selector silver                    # a named selector group
hpt run-dbt --command build --select gld_+                       # the full Gold layer
hpt run-dbt --command test --hospital-ids vumc
```

The dbt project defines layer selectors — `staging`; `silver_base`,
`silver_core`, `silver_review_queue`, `silver_audit`, `silver`; `validation`;
and `gold_core`, `gold_dimension`, `gold_marts`, `gold_scorecards`, `gold` —
and `gold_bi`, plus the pipeline selectors `pipeline_snapshot_metadata` and
`pipeline_charge_data` and the operational `audit`, `audit_staging`, and
`audit_marts` selectors. Pass one with `--selector`, or use `--select` with dbt
node syntax (`model`, `model+`, `+model`) for arbitrary targets.

`hpt run-dbt` defaults to the complete dbt graph so snapshot-grained
consumers, Silver tables, and cross-model tests stay coherent. Pass `--selector`
(named selectors) or `--select` (model node selection with dbt graph operators
such as `model+`, mutually exclusive with `--selector`) for an intentionally
partial run. Per-snapshot runs, including `--full-refresh`, accept partial
selectors. For multi-snapshot rebuilds, `--defer-tests` materializes every
snapshot first and runs the whole-table tests once at the end instead of after
each snapshot.

Snapshot-grained incremental models use the custom `snapshot_replace` strategy.
It deletes rows for the explicitly requested `snapshot_ids` before inserting
the new model result, so a successful rebuild that produces zero rows still
removes the snapshot's prior rows. Repeat incremental runs require a non-empty
snapshot scope; pass `--hospital-ids` (or `--snapshot-ids`) to `hpt run-dbt`.
Use `hpt run-dbt --full-rebuild` for an unscoped full refresh, or build in
`--hospital-ids` batches at full-corpus scale to bound memory.

When a build fails partway it can leave a snapshot partially materialized across
the Silver and validation tables. `hpt clear-snapshot --snapshot-ids <id>`
deletes that snapshot's rows from every snapshot-grained table so it is no longer
partial; raw files, snapshot metadata, and Bronze partitions are untouched, so
re-running dbt for the snapshot rebuilds it cleanly. Pass
`hpt run-dbt --clear-on-failure` to do this automatically when a build/run fails:
per-snapshot runs clear the failing snapshot, scoped runs clear the whole scoped
set. Canonical staging views remain unscoped and are intentionally not changed
by `clear-snapshot`.

## Runtime Configuration

Most local runs work with defaults. The main overrides are:

| Variable | Purpose | Default |
|---|---|---|
| `HPT_RAW_STORAGE_BASE_URI` | Raw downloads and snapshot metadata root | `file://.../data` |
| `HPT_BRONZE_ROOT` | Parsed Bronze Parquet root | `data/bronze` |
| `HPT_QUARANTINE_ROOT` | Parser validation failures | `data/quarantine` |
| `HPT_AUDIT_ROOT` | Queryable command run and attempt audits | `data/audit` |
| `HPT_REFERENCE_ROOT` | External reference Bronze Parquet root | `data/reference/bronze` |
| `HPT_REFERENCE_RAW_ROOT` | External reference raw cache | `data/reference/raw` |
| `HPT_REGISTRY_PATH` | Optional hospital registry override | bundled registry |
| `HPT_DUCKDB_PATH` | dbt DuckDB database path | `data/hpt.duckdb` |
| `HPT_SILVER_RETENTION_MODE` | Silver/validation retention, `current_only` or `all_snapshots` | `current_only` |

See `docs/configuration.md` for all environment variables, precedence rules, and
HTTP client settings.

## Architecture

The pipeline follows a medallion pattern:

```mermaid
flowchart LR
  registry[Hospital Registry] --> download[Download]
  download --> raw[Raw MRF Files]
  download --> snapshots[Snapshot Metadata]
  raw --> bronze[Bronze Parquet]
  snapshots --> bronze
  bronze --> silver[dbt Silver Models]
  silver --> review[Review Queues]
  silver --> gold[dbt Gold Models]
  gold --> bi[gld_bi Presentation Marts]
  bi --> evidence[Evidence Public Reports]
```

Python owns:

- hospital registry loading;
- HTTP download and retry behavior;
- raw file and snapshot metadata storage;
- compression handling and MRF layout sniffing;
- JSON and CSV structural parsing;
- Bronze Parquet writing and quarantine output.

dbt owns:

- external Bronze source definitions for DuckDB;
- external audit source definitions and operational audit views;
- staging views over Bronze;
- Silver Base normalization across JSON and CSV inputs;
- Silver Core payer identity and payer/plan context enrichment;
- review queues and data quality tests.

Bronze intentionally preserves source values and lineage. Business
normalization, payer matching, code interpretation, and analytics-friendly
shaping belong in dbt models.

## Data And Lineage

Downloaded MRFs can be large and are not committed to git. Runtime output is
local by default and ignored:

- `data/raw/` for source files;
- `data/metadata/` for snapshot metadata;
- `data/bronze/` for parsed Parquet;
- `data/quarantine/` for validation failures;
- `data/audit/` for append-only invocation and attempt audit Parquet;
- `data/hpt.duckdb` for local dbt/DuckDB work;
- `logs/` for CLI run logs and failure summaries.

Snapshot lineage is a core design constraint. Downstream tables preserve
identifiers such as `snapshot_id`, `file_hash`, source URL, source filename, and
ingest timestamps so modeled rows can be traced back to the source file.

Each `hpt download`, `hpt ingest`, and `hpt run-dbt` invocation receives a
unique `run_id`. Inspect a run with `hpt show-run --run-id <run-uuid>`.
Separate command invocations can be correlated through their shared
`snapshot_id`.

## Example Use Case

One intended workflow is comparing negotiated payer rates across hospitals after
normalizing charge items, payer identities, and plan context. The pipeline keeps
the source file lineage intact while converting heterogeneous JSON and CSV MRFs
into dbt models that can support cross-hospital rate analysis.

## Documentation

Start with:

- `docs/architecture/pipeline-overview.md`
- `docs/architecture/medallion-layers.md`
- `docs/architecture/storage-layout.md`
- `docs/architecture/bronze-schema.md`
- `docs/architecture/silver-schema.md`
- `docs/architecture/gold-schema.md`
- `docs/domain/hpt-glossary.md`
- `docs/domain/cms-mrf-schema-notes.md`
- `docs/domain/hospital-registry-rules.md`
- `docs/development/getting-started.md`
- `docs/development/testing-strategy.md`
- `docs/development/bi-layer.md`
- `docs/decisions/0020-use-evidence-for-public-bi.md`
- `apps/evidence/README.md`

Tracked docs are the authoritative reviewer-facing documentation. Historical
notes and local research material are intentionally kept out of the tracked docs.

## Current Limitations

- The bundled registry is curated for development and research coverage, not a
  complete national hospital registry.
- Publisher MRF URLs can change or disappear; failed downloads should be
  investigated against the registry and source hospital pages.
- Gold cross-hospital percentile and benchmark output is only as broad as the
  loaded corpus: cohorts below the 3-hospital denominator publish no percentiles
  (the rows remain, flagged `below_min_hospital_denominator`). See
  `docs/architecture/gold-schema.md`.
- The shipped analytics goal is comparing *current* prices across hospitals.
  Price-change-over-time analysis is a deliberate extension point, not a v1
  deliverable: there is no longitudinal corpus to build or validate it against
  within this project's scope. The architecture keeps the seam open for it —
  snapshot lineage, the `all_snapshots` retention mode, and a validated
  cross-snapshot service identity — so an adopter who runs the pipeline
  continuously can add history without reworking the model. See
  `docs/decisions/0016-scope-history-as-extension-point.md`.
- Airflow, Docker, and Terraform directories are placeholders.
- This project is not medical, billing, legal, or compliance advice.

## License

This project is licensed under the [Apache License 2.0](LICENSE.md).
