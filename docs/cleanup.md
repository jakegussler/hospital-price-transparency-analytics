# Cleanup And Alignment Notes

This file tracks known inconsistencies discovered while building project
documentation. These are not fixed by the documentation pass unless explicitly
called out in a later implementation task.

## Transform Alignment

- Silver and Gold dbt directories exist but do not contain production models yet. (leave this for now)

## Planning Notes

- `docs/notes/` contains useful historical planning and research, but it should
  not be treated as the primary onboarding path.
- Some planning notes describe Airflow, MinIO, Metabase, Docker Compose, and
  Terraform as future architecture. The current repo contains placeholders, not
  active implementations for those systems.

## Script Notes

- Some ad hoc scripts may be useful references but are not maintained as stable
  command-line tools. (this is fine for the scripts in adhoc/scripts)
