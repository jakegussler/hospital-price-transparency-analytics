# Cleanup And Alignment Notes

This file tracks known inconsistencies discovered while building project
documentation. These are not fixed by the documentation pass unless explicitly
called out in a later implementation task.

## Transform Alignment

- Gold dbt directories exist but do not contain production models yet. (leave
  this for now)
- Silver Base, Silver Core, and review queue models are implemented and
  documented in `docs/architecture/silver-schema.md`.
- The JSON streaming parser validates individual `standard_charge_information`
  and `modifier_information` objects structurally, but it still does not run the
  root `CMSMRFJson` model over entire files. Header/root required-shape gaps are
  therefore surfaced through Bronze header rows and dbt validation rather than
  parser quarantine.
- The Bronze layer materializes empty Parquet files for optional tables a
  parser emits but that have no rows (e.g. a snapshot without
  `general_contract_provisions`), so their partition directory always exists.
  Format-specific tables a parser never emits at all (e.g. `csv_charge_rows`
  for a JSON-only corpus) can still produce an empty-glob `read_parquet` error
  in staging; ingest at least one file of each format, or guard those sources,
  before running dbt.

## Planning Notes

- `docs/notes/` contains useful historical planning and research, but it should
  not be treated as the primary onboarding path.
- Some planning notes describe Airflow, MinIO, Metabase, Docker Compose, and
  Terraform as future architecture. The current repo contains placeholders, not
  active implementations for those systems.

## Script Notes

- Some ad hoc scripts may be useful references but are not maintained as stable
  command-line tools. (this is fine for the scripts in adhoc/scripts)
