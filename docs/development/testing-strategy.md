# Testing Strategy

The project uses pytest for Python behavior and dbt architecture checks, dbt
tests for warehouse behavior, and small isolated DuckDB fixtures for focused
transform runtime guarantees.

## Test Commands

```bash
make test
pytest tests/
```

The transform architecture and isolated runtime checks are part of the pytest
suite. Run them directly while changing dbt scoping:

```bash
pytest tests/transform/
```

Lint and format checks:

```bash
make lint
make format
```

## Test Layout

```text
tests/
  conftest.py
  fixtures/
  ingest/
  loaders/
  parsers/
  pipeline/
  transform/
  test_config.py
  test_download.py
  test_registry.py
  test_snapshot.py
  test_storage.py
```

## What To Test

Config changes:

- Environment variable precedence.
- CLI override behavior.
- Default path behavior.

Registry changes:

- Valid records load.
- Missing fields fail.
- Invalid enum values fail.
- Duplicate hospital IDs fail.

Storage and snapshot changes:

- Hive-style path construction.
- fsspec read/write behavior.
- Latest-snapshot resolution by `valid_from` recency (currentness is derived in
  dbt, not stored, so there is no Python-side expiration to test).
- Hash-based unchanged behavior.

Parser changes:

- JSON streaming behavior for representative nested records.
- CSV header extraction.
- CSV Tall row mapping.
- CSV Wide payer-column unpivoting.
- Schema-stable empty DataFrames.
- Quarantine behavior for isolated validation failures.

Pipeline changes:

- Snapshot resolution.
- Parser selection.
- Compressed file materialization.
- Bronze writer integration.
- Failure artifacts and structured logging.
- Append-only audit run/attempt records, terminal status, and audit-write
  failure behavior.

dbt changes:

- Add dbt tests beside models where practical.
- Validate expected model grain with `unique` and `not_null` tests.
- Assert each Silver model's **natural row grain**, not just its surrogate key.
  Surrogate keys are positional (built from source ordinals), so a `unique`
  surrogate-key test does not prove the business grain. Document the grain in the
  model description and lock it with `dbt_utils.unique_combination_of_columns`.
  Use **error** severity only where the grain is structurally guaranteed; use
  **warn** where source faithfulness allows legitimate repeats (e.g. duplicate
  CMS codes on one item, byte-identical JSON contexts), routing those repeats to
  an audit/observability model rather than dropping rows.
- Match enum and disposition severity to the validation framework: an enum the
  validation layer rejects (e.g. `setting`) can carry an **error** `accepted_values`
  guard; an enum it only reports (e.g. `billing_class`, which CMS documents as
  recommended) must be **warn** so source-faithful out-of-enum values are not
  failed.
- `dbt_utils` is a project dependency (`transform/packages.yml`). Run
  `make dbt-deps` once after cloning or changing packages so the package is
  installed before any `hpt run-dbt` build; CI installs dbt packages in its
  transform jobs.
- Keep source definitions aligned with actual Bronze table output.
- Validate changes with the smallest relevant snapshot-scoped run, preferring
  node selection over a named selector:
  `hpt run-dbt --snapshot-ids <id> --command build --select <model>+`. Use a
  named `--selector` only when a tag group is the right unit. When the local
  warehouse holds stale rows from snapshots that predate a model column, scoped
  runs leave those rows in place and their `not_null`/enum tests can fail on the
  stale slice; verify on a fresh isolated warehouse (the offline e2e fixture run
  does this) and treat the stale failures as a warehouse-state issue, not a
  regression.
- Know how each test kind responds to snapshot scope. In a **scoped `build`**,
  **singular** tests in `transform/tests/*.sql` reference models through
  `hpt_scoped_ref`, so they check only the scoped snapshot's rows, while
  **generic** tests in the `_*.yml` files (`not_null`, `accepted_values`,
  `relationships`, `unique_combination_of_columns`) always check the whole
  materialized table. The generic ones are what makes a repeated multi-snapshot
  `build` re-test already-built snapshots.
- `--defer-tests` does **not** skip or per-snapshot the singular tests. It
  materializes every snapshot with `run` (which executes no tests), prunes, then
  runs a single **unscoped** `test` pass. Unscoped means no `snapshot_ids` var, so
  `hpt_scoped_ref` adds no filter and the singular tests check the *whole* table
  too — every current snapshot at once, after the prune has removed non-current
  rows. You do not pass the snapshot IDs into that pass; an empty scope already
  means "all of it." So both singular and generic tests run exactly once, against
  the full current table (see `snapshot-scoped-runs.md`).
- Never invoke dbt directly or run an unscoped/full-corpus dbt target during
  agent validation.

## dbt Scoping Tests

`tests/transform/test_scoping_invariants.py` runs `dbt parse`, reads the
generated manifest, and enforces the architecture established by ADR 0012:

- staging views contain no run-scope macros;
- Bronze and staging inputs are scoped at snapshot-grained consumers;
- accumulated snapshot-grained inputs are explicitly scoped, including inputs
  reached through ephemeral models;
- the snapshot-grained incremental models in the manifest match
  `hpt_snapshot_grained_incremental_models()`.

This is a manifest-aware architecture check, not a raw source grep. It requires
dbt to be installed but does not require a warehouse connection.

`tests/transform/test_scoped_input_runtime.py` uses a temporary in-memory DuckDB
and two tiny snapshot partitions to verify:

- a consumer-side predicate prunes the Parquet scan to one partition;
- canonical staging remains queryable across both snapshots;
- a scoped incremental replacement leaves the unrelated snapshot untouched;
- an empty scope reads all available snapshots.

`tests/transform/test_snapshot_replace_runtime.py` builds a temporary dbt project
with the real `snapshot_replace` macros and verifies nonzero replacement,
zero-row replacement, multi-snapshot deletion, output-scope validation and
rollback, rejection of unscoped incremental runs, and unscoped full refresh.

For model-level integration validation, use a small snapshot scope and the
smallest relevant selector or `--select` graph. Full-refresh or full-rebuild
parity must be verified outside the agent workflow when required; record that
limitation rather than running an unscoped corpus build.

## Fixture Guidance

Use small, explicit fixtures. Prefer tiny JSON/CSV samples that isolate one
schema behavior over large copied source files.

Good fixtures should:

- Preserve CMS shape.
- Include edge cases for nulls and optional fields.
- Include enough rows to prove grain and key behavior.
- Avoid committing real downloaded MRFs or local data outputs.

## Coverage Gaps To Watch

Known gaps as of this documentation pass:

- No end-to-end test that downloads, ingests, reads Bronze through dbt, and
  validates DuckDB output.
- No automated fixture-warehouse test runs the complete snapshot-scoped dbt
  graph against two snapshots and verifies materialized-table isolation.
- No automated fixture-warehouse test runs the full Gold comparison/benchmark
  graph across a multi-hospital corpus large enough to publish percentile output.
  Silver and validation models have dbt tests; add or update focused tests when
  changing model grain, rejection behavior, or cross-model relationships.

## Docs-Only Changes

For documentation-only changes, run tests only when the docs modify commands,
configuration, or assumptions that need source verification. Always verify that
documented commands match the current CLI and Makefile behavior.
