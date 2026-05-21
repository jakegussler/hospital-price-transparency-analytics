# Cleanup And Alignment Notes

This file tracks known inconsistencies discovered while building project
documentation. These are not fixed by the documentation pass unless explicitly
called out in a later implementation task.

## Command Alignment

- `Makefile` has a `parse` target that calls `hpt parse`, but the current CLI
  exposes `hpt download` and `hpt ingest`. Documentation should use
  `hpt ingest` unless the CLI changes.
- `Makefile` has Docker targets, but there is no root `docker-compose.yml` yet.
  Treat Docker as planned infrastructure.

## Configuration Alignment

- Python ingest uses `HPT_PARSED_BRONZE_ROOT` for parsed Bronze output.
- dbt uses `HPT_BRONZE_ROOT` for external Bronze sources.
- Local development should point both at the same directory when overriding
  defaults.

## Transform Alignment

- `docs/bronze_layer.md` documents `csv_charge_rows`.
- `transform/models/staging/_bronze_sources.yml` does not currently declare
  `csv_charge_rows`.
- Silver and Gold dbt directories exist but do not contain production models yet.

## Registry Alignment

- The active bundled registry is `src/hpt/registry/hospitals.yml`.
- Top-level `registry/hospitals.yaml` uses a different shape and is not currently
  the loader default.
- `registry/hospitals.md` is empty.

## Planning Notes

- `docs/notes/` contains useful historical planning and research, but it should
  not be treated as the primary onboarding path.
- Some planning notes describe Airflow, MinIO, Metabase, Docker Compose, and
  Terraform as future architecture. The current repo contains placeholders, not
  active implementations for those systems.

## Source Comments And Stubs

- `src/hpt/pipeline/ingest_snapshot.py` may contain stale comments/docstrings
  from before CSV parsers were wired in.
- `src/hpt/quality/observations.py` is a stub-level module and does not yet have
  corresponding docs or tests.
- Some ad hoc scripts may be useful references but are not maintained as stable
  command-line tools.
