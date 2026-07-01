# HPT Evidence App

Public Evidence.dev dashboard/reporting surface for the Gold BI presentation
marts.

## Workflow

Run all commands from the repository root unless noted.

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

Production build check:

```bash
cd apps/evidence
npm run sources
npm run build
npm run preview
```

Use `npm run dev -- --port 4000` if port 3000 is occupied.

## Data Contract

Evidence reads only the generated Parquet files under
`sources/hpt/data/`. The exporter writes those files from the six allowlisted
`main_gold.gld_bi__*` marts after dbt completes. Evidence SQL should query
`hpt.<source_name>` tables only; comparability, denominator, trust, payer
matching, and amount semantics belong in dbt.

Generated Parquet files and local Evidence state are ignored by git.

