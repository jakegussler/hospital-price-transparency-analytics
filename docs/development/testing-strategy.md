# Testing Strategy

The current test suite is pytest-based and focuses on the Python ingest pipeline.

## Test Commands

```bash
make test
pytest tests/
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

dbt changes:

- Add dbt tests beside models where practical.
- Validate expected model grain with `unique` and `not_null` tests.
- Keep source definitions aligned with actual Bronze table output.

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
- No implemented Silver/Gold model tests because those models are not built yet.

## Docs-Only Changes

For documentation-only changes, run tests only when the docs modify commands,
configuration, or assumptions that need source verification. Always verify that
documented commands match the current CLI and Makefile behavior.
