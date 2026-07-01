# HPT Evidence App

Public Evidence.dev dashboard/reporting surface for the Gold BI presentation
marts.

Markdown routes live in `pages/`, which the pinned Evidence CLI copies into its
generated `.evidence/template/src/pages/` workspace at dev/build time.

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

Use `npm run dev -- --port 4000` if port 3000 is occupied.

`npm run sources` includes a narrow post-processing step for zero-row marts:
Evidence can emit a zero-byte static Parquet file when a source query returns no
rows, even though the exported source Parquet is valid. The repair step copies
the valid source Parquet over only those zero-byte generated files.

`npm run dev` also clears generated Evidence/SvelteKit dev caches before
starting the server. This avoids stale `.evidence/template` state after a
crashed dev process without removing exported source Parquet files.

## Data Contract

Evidence reads only the generated Parquet files under
`sources/hpt/data/`. The exporter writes those files from the six allowlisted
`main_gold.gld_bi__*` marts after dbt completes, including schema-valid empty
tables for smoke runs. Evidence SQL should query `hpt.<source_name>` tables
only; comparability, denominator, trust, payer matching, and amount semantics
belong in dbt.

Generated Parquet files and local Evidence state are ignored by git.
