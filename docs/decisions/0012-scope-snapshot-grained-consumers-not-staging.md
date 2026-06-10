# 0012: Scope Snapshot-Grained Consumers, Not Staging Views

Status: accepted

## Context

Bronze Parquet is hive-partitioned by `snapshot_id`, and snapshot-grained Silver
and validation models are incremental tables that use `delete+insert` with
`snapshot_id` as the batch key. Snapshot-scoped runs must therefore do two
things:

- push a `snapshot_id` predicate into Bronze reads so DuckDB prunes unrelated
  Parquet partitions;
- ensure incremental models emit only the requested snapshot batch so unrelated
  retained rows are not deleted and reinserted.

The original implementation placed `hpt_snapshot_filter()` in every
`stg_bronze__*` model. Because staging models are persisted views, each scoped
dbt run baked its requested snapshot IDs into the view definitions. Staging
therefore exposed whichever snapshot batch the most recent dbt invocation had
processed instead of acting as a stable view over the Bronze corpus.

An alternative was to keep canonical staging unscoped and add a parallel
ephemeral `scoped_bronze__*` model for each staging model. That would duplicate
the staging hierarchy without preventing consumers from bypassing it or reading
accumulated snapshot-grained tables unscoped.

## Decision

Staging views are canonical, unscoped views over all available Bronze
partitions. They own source typing and light cleanup, independent of the current
run scope.

Snapshot-grained consumers own execution scoping at every input that can contain
more snapshots than the requested batch:

- `hpt_scoped_source(source_name, table_name)` scopes direct Bronze reads.
- `hpt_scoped_ref(model_name)` scopes staging and accumulated snapshot-grained
  model reads.

Both macros apply `hpt_snapshot_filter()` inside a derived table. With a
non-empty `snapshot_ids` var, they restrict the input to the requested batch.
With no `snapshot_ids`, they read all snapshots, preserving full-rebuild
behavior.

Every snapshot-grained input is scoped explicitly rather than relying on filter
propagation through joins. This includes rejection keysets and accumulated
Silver/validation tables. The manifest-aware architecture test requires all such
edges to be scoped; the accumulated-input allowlist is empty.

Cross-snapshot models remain unscoped. This includes global dimensions, review
queues, and the `hpt_resolved_snapshot_state_sql()` currentness resolver. The
resolver intentionally reads complete Bronze snapshot history so currentness is
correct during scoped runs.

## Enforcement

`tests/transform/test_scoping_invariants.py` parses the dbt manifest and asserts:

- all 15 `stg_bronze__*` models are unscoped;
- every non-staging Bronze or staging dependency uses a scoped-input macro;
- every snapshot-grained model dependency uses `hpt_scoped_ref()`, including
  dependencies reached through ephemeral models;
- the manifest's snapshot-grained incremental model set matches
  `hpt_snapshot_grained_incremental_models()`.

`tests/transform/test_scoped_input_runtime.py` uses an isolated DuckDB fixture to
verify partition pruning, unscoped staging explorability, full-scope fallback,
and incremental isolation.

## Consequences

- Staging is stable for exploration, documentation, and tests before and after
  snapshot-scoped runs.
- Snapshot-scoped consumers preserve Bronze partition pruning and incremental
  isolation.
- Adding a snapshot-grained dependency without explicit scoping fails the
  manifest architecture test.
- Full-rebuild behavior remains unscoped when `snapshot_ids` is absent.
- Consumer SQL contains explicit scoped-input wrappers at processing
  boundaries.
- The intentionally unscoped currentness resolver must remain separate from the
  scoped staging input in `slv_base__hospital_snapshots`.
