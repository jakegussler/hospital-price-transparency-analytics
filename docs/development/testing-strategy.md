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
- Keep source definitions aligned with actual Bronze table output.
- Validate changes with the smallest relevant snapshot-scoped
  `hpt run-dbt --snapshot-ids <id> --command build --selector <selector>` run.
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

For model-level integration validation, use one pinned local snapshot and the
smallest relevant selector. Full-refresh or full-rebuild parity must be verified
outside the agent workflow when required; record that limitation rather than
running an unscoped corpus build.

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
- Gold model tests are not present because Gold models are not implemented yet.
  Silver and validation models have dbt tests; add or update focused tests when
  changing model grain, rejection behavior, or cross-model relationships.

## Docs-Only Changes

For documentation-only changes, run tests only when the docs modify commands,
configuration, or assumptions that need source verification. Always verify that
documented commands match the current CLI and Makefile behavior.
