# Multi-Snapshot Service-Item Continuity Validation

The deterministic `service_item_id` (decision
[0014](../decisions/0014-derive-service-item-identity-deterministically.md))
exists to give the *same charge item the same id across successive MRF
publications of one hospital*, so Gold can track price-over-time. Under the
default `current_only` retention every hospital holds exactly one snapshot, so
`snapshot_count = 1` everywhere and that cross-snapshot key is never exercised
against real-shaped data.

You cannot get a second snapshot organically: `hpt download` dedupes by file
hash, so re-downloading an unchanged file writes no new snapshot, and real
republished files are gated on time / orchestration. This validation
manufactures a controlled second snapshot for two fictional hospitals and runs
them through the real parser → Bronze → Silver path, so the identity logic is
exercised on realistic data now, decoupled from orchestration.

## What is built

| Artifact | Purpose |
|---|---|
| `scripts/build_multi_snapshot_corpus.py` | Generates two-snapshot synthetic CSV-tall MRFs for two fictional hospitals and ingests them into an **isolated** Bronze root. |
| `slv_audit__service_item_continuity` | Per-hospital scorecard: multi-snapshot %, items minted in / retired before the latest snapshot. The view that makes continuity *measured*, not asserted. |
| `core_service_item_id_hospital_scope_guard` (singular test) | Fails the build if any `service_item_id` spans hospitals (enforces the 0014 cross-hospital boundary). |
| `service_item_id_hospital_scope_and_mint` (unit test) | Pins that identical code+description in different hospitals get different ids, and a token-set-changing rewrite mints a new id. |

The two fictional hospitals (`zzz-msval-continuity`, `zzz-msval-overmerge`) live
in a dedicated fixtures seed,
`transform/seeds/fixtures/hospitals_validation_fixtures.csv` (tag
`validation_fixtures`), kept **out** of the registry-faithful `hospitals` seed.
They are unioned into `slv_base__hospitals` only when the
`hpt_include_validation_fixtures` var is true (set
`HPT_INCLUDE_VALIDATION_FIXTURES=true`), so the service-item referential test
passes during validation. A normal production run leaves the var false and never
sees them, so `hospitals.csv` stays a faithful export of the bundled registry.

## Mutation classes exercised

Between snapshot `v1` (2025-01-01) and `v2` (2025-06-01):

| Class | Expectation |
|---|---|
| identical item recurs | same id, `snapshot_count = 2` |
| word-order / punctuation drift | same id (token signature is order-insensitive) |
| price change only | same id (amount is not identity) |
| drug quantity change only | same id (`drug_unit` excluded from identity) |
| token-set-changing rewrite | **new** id minted; the old id retires at v1 |
| new item, v2 only | `snapshot_count = 1`, first seen = latest |
| shared specific code + token-equal descriptions within a snapshot | one `service_item_id` over multiple source items → `slv_audit__service_item_overmerge` finding, well under the over-merge guard threshold (> 10) |

## Run it

The corpus is written to an isolated root (`data/multi_snapshot_validation/`) and
validated in a throwaway DuckDB so the production warehouse is never touched.

> Validating multi-snapshot continuity is **outside the agent dbt-safety
> envelope** (it materializes more than one snapshot per hospital at once and
> uses `all_snapshots` retention). Run it manually, as below — do not expect a
> single scoped agent run to cover it.

```bash
# 1. Build the isolated synthetic corpus (idempotent).
.venv/bin/python scripts/build_multi_snapshot_corpus.py build
.venv/bin/python scripts/build_multi_snapshot_corpus.py list   # prints the snapshot ids

# 2. Point dbt at the isolated root + a throwaway DuckDB, under all_snapshots.
export ISO_ROOT="$PWD/data/multi_snapshot_validation"
export HPT_RAW_STORAGE_BASE_URI="$ISO_ROOT"
export HPT_BRONZE_ROOT="$ISO_ROOT/bronze"
export HPT_QUARANTINE_ROOT="$ISO_ROOT/quarantine"
export HPT_DUCKDB_PATH=/tmp/hpt_msval.duckdb
export HPT_SILVER_RETENTION_MODE=all_snapshots
export HPT_INCLUDE_VALIDATION_FIXTURES=true   # union the fixture hospitals into slv_base__hospitals
SNAPS=ccce3b9a-793f-53d0-b12c-3549cf3a7a99,576ad522-4e4d-5a68-82f8-345dbc86d931,690b5611-4870-51c2-a58e-981f158cf1d5,294270d1-ebbc-50c3-b495-79ef3a3b1e3a

# 3. Materialize the whole chain, then run the Silver tests.
hpt run-dbt --snapshot-ids "$SNAPS" --command run \
  --selector "staging,validation,silver_base,silver_core,silver_audit" --seeds
hpt run-dbt --snapshot-ids "$SNAPS" --command test --selector "silver_core,silver_audit"
```

`--defer-tests` automates this materialize-then-test split for a single
selector or `--select` graph: `hpt run-dbt --snapshot-ids "$SNAPS" --command
build --defer-tests --selector silver_core` runs every snapshot with `run`,
prunes, then runs one unscoped `test` pass — avoiding the whole-table generic-test
re-scan after each snapshot. See `snapshot-scoped-runs.md` for the trade-offs.

Inspect the scorecard:

```sql
select * from main.slv_audit__service_item_continuity where hospital_id like 'zzz-msval%';
select * from main.slv_audit__service_item_overmerge   where hospital_id like 'zzz-msval%';
```

## Expected result (verified 2026-06-16)

`slv_audit__service_item_continuity`:

| hospital_id | snapshots | items | multi-snapshot | pct | minted | retired |
|---|---|---|---|---|---|---|
| zzz-msval-continuity | 2 | 8 | 5 | 0.625 | 2 | 1 |
| zzz-msval-overmerge | 2 | 2 | 2 | 1.0 | 0 | 0 |

For `zzz-msval-continuity` the five recurring items (stable, drifted, price-changed,
drug-quantity-changed, categorical, uncoded) carry `snapshot_count = 2`; the token
rewrite and the v2-only item are the two mints; the old id of the rewrite is the one
retirement. `slv_audit__service_item_overmerge` flags exactly the shared-code pair
(`max_snapshot_source_items = 2`), and the hospital-scope guard returns zero rows.

All Silver Core / audit data tests pass, including the
`service_items → hospitals` referential check. Unit tests are excluded from
snapshot-scoped `hpt run-dbt` invocations and are covered by the dedicated
CI/maintainer path.

## Caveats and cleanup

- **Unit tests need `test_type:unit`.** `hpt run-dbt --selector silver_core` runs
  the data tests but not the unit tests; keep unit-test validation separate from
  this snapshot-scoped workflow.
- **`current_only` keeps it latent.** Re-run under `HPT_SILVER_RETENTION_MODE=all_snapshots`;
  otherwise the prune drops the older snapshot and `snapshot_count` collapses to 1.
- **Remove the corpus** with
  `.venv/bin/python scripts/build_multi_snapshot_corpus.py clean` (isolated root only).
- **Want your production full refresh to demonstrate continuity?** Build into the
  production root instead with `--root "$PWD/data"` and run the refresh under
  `all_snapshots`. This injects the (tiny, clearly-labeled) synthetic corpus into
  the main Bronze; reverse it with the same `clean --root "$PWD/data"`.

## Extension-point follow-up

This validation exercises the *mechanics* of continuity and drift, which is all
v1 needs. Supersession links (`valid_from` / `valid_to` on
`slv_core__service_items`) and over-merge threshold calibration against true
churn are **out of v1 scope** — they belong to the price-history extension point
(decision [0016](../decisions/0016-scope-history-as-extension-point.md)), which
is deliberately not built because there is no real accumulating corpus to
validate it against. They would only be picked up alongside orchestrated
multi-snapshot accumulation. Tracked in [cleanup.md](../cleanup.md).
