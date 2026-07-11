# HPT Evidence App

Public Evidence.dev dashboard/reporting surface for the Gold BI presentation
marts.

Markdown routes live in `pages/`, which the pinned Evidence CLI copies into its
generated `.evidence/template/src/pages/` workspace at dev/build time. Shared
Svelte components (e.g. `SiteCallout`) live in `components/`. Do not name a
custom component after an Evidence built-in (`Callout` is a chart annotation in
core-components and will shadow yours).

## Site structure

- `/` — corpus overview: headline KPIs, the comparability funnel, featured
  comparisons, data-confidence bands.
- `/compare` + `/compare/[service_slug]` — service price exploration; routes
  use the URL-safe `service_url_slug`, not the md5 `service_code_key`.
- `/hospitals` + `/hospitals/[hospital_id]` — scoreboard and per-hospital
  report cards (scores, funnel, market positions, cash comparisons, blockers).
- `/payers` + `/payers/[canonical_payer_id]` — matched-insurer views.
- `/data-quality` — funnel, all 11 blocker explanations, thin contexts.
- `/methodology` (+ `prices`, `comparability`, `scores`), `/glossary` —
  plain-language rules, thresholds, and definitions.
- `/downloads` — real download links + the generated data dictionary.
- `/about` — scope, corpus roster, corrections path, release notes.

Copy rules: every ranking/statistic shows its hospital count ("n") and status;
different amount kinds are never ranked against each other; thin cohorts are
labeled, never dropped; scores are described as published-data usability, never
legal compliance; markdown links do not render inside component slots — use
`<a href>` inside `SiteCallout`.

## Workflow

Run all commands from the repository root unless noted.

Smoke verification can use a small corpus, including one hospital. The exporter
requires every allowlisted BI mart to exist, but it allows empty Parquet outputs
because denominator-gated comparison marts can be legitimately empty on tiny
corpora.

```bash
hpt run-dbt --command build --selector gold_bi
hpt run-dbt --command test --selector gold_bi
uv run python scripts/export_evidence_artifact.py --replace
cd apps/evidence
nvm use
npm ci
npm run sources
npm run dev
```

For a public demo corpus, run the optional readiness gate before exporting. It
checks that the key BI marts have enough rows for the default report views.

```bash
uv run python scripts/check_evidence_readiness.py
uv run python scripts/export_evidence_artifact.py --replace
```

Production build check:

```bash
cd apps/evidence
npm run sources
npm run build
npm run preview
```

For an automated public-site build, configure the required storage and DuckDB
environment variables, then run `scripts/build_public_site.sh` from the
repository root. The script performs download, ingest, memory-bounded dbt builds,
readiness checks, artifact export, and the static Evidence build. If
`HPT_PUBLIC_SITE_S3_URI` is set, it also syncs the completed `build/` directory
to that S3 URI.

Use `npm run dev -- --port 4000` if port 3000 is occupied.

`npm run sources` includes a narrow post-processing step
(`scripts/fix-empty-parquet-sources.mjs`): Evidence's source extraction can
emit a zero-byte static Parquet file for a zero-row source, or skip rewriting
it entirely and leave a stale file whose schema no longer matches. The repair
step copies the valid exported source Parquet over any missing, zero-byte, or
stale generated file.

`npm run dev` also clears generated Evidence/SvelteKit dev caches before
starting the server. This avoids stale `.evidence/template` state after a
crashed dev process without removing exported source Parquet files.

## Data Contract

Evidence reads only the generated Parquet files under `sources/hpt/data/`. The
exporter writes those files from the nine allowlisted `main_gold.gld_bi__*`
marts after dbt completes (see decision 0020, amended 2026-07-07), plus two
generated artifacts:

- `public_metadata.parquet` — export provenance per table, including the
  `build_id` git identifier and download-bundle CSV file names.
- `public_data_dictionary.parquet` — table/column documentation parsed from
  `transform/models/gold/bi/_gold_bi_models.yml`; those yml descriptions are
  public documentation.

The exporter also writes the public download bundle into `static/downloads/`
(Parquet + CSV per mart, the dictionary, and a generated README; CSVs over
25 MB ship as `.csv.gz`). Both `sources/hpt/data/` and `static/downloads/` are
git-ignored generated outputs.

Evidence SQL should query `hpt.<source_name>` tables only; comparability,
denominator, trust, payer matching, and amount semantics belong in dbt. Page
SQL may filter, sort, limit, and 1:1 label-map enum values for display, but
must never reclassify statuses, bands, or floors.

## Deployment note (static prerendering)

`npm run build` prerenders the pages reachable through links in rendered
tables. Parameterized routes that are not linked anywhere (e.g. a service slug
only reachable via client-side filtering) are not emitted as static HTML, so
the deploy target needs a fallback rewrite for unknown paths (or accept 404s
for unlinked deep links). Corpora with comparable contexts link far more
service pages through the compare hub and featured tables.
