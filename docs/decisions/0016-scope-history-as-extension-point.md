# 0016: Scope Price History As An Extension Point, Not A v1 Deliverable

Status: accepted

## Context

The project's analytics goal had been framed as two parallel tracks: comparing
prices *across hospitals* (current) and comparing prices *over time* (history).
The current-comparison track is the foundation Gold Phase 1/2 is built on; the
history track centers on a future `gld__price_change_history` mart plus
service-item supersession and over-merge threshold calibration.

Reassessing history on its own merits, not on the earlier planning assumption
that it must ship:

- **No longitudinal data exists, and none will accumulate within this project's
  horizon.** History needs multiple snapshots per hospital under `all_snapshots`
  retention, produced by orchestration that is not built. Long-term storage of
  every snapshot is also not affordable here, so even with orchestration the
  accumulated history would stay shallow.
- **It cannot be demonstrated or tested against real data.** Published results
  (README numbers, example analyses) would all be current-snapshot results. A
  history mart would ship with synthetic-only validation and no real findings.
- **It is already architecturally decoupled.** Per the Gold design principle
  "current and history are separate models sharing definitions," Gold Phase 1
  (current comparison) and Phase 2 (benchmarks) have no dependency on history.
  The history work was already sequenced last (roadmap Milestone E), gated on
  orchestration.

The one real cost of dropping it is the open-source / org-adoption story: an
adopter running this pipeline continuously *would* want history. That goal is
served by preserving the architectural seam, not by shipping an unvalidatable
mart now.

## Decision

Price history is a **documented extension point**, not a v1 deliverable. The
project's stated analytics goal is cross-hospital comparison of current prices;
history is something the architecture is deliberately shaped to support later,
built by an adopter (or a future phase) once orchestrated multi-snapshot
accumulation exists.

**Keep (cheap seam, also serves current analysis):**

- `snapshot_id` / `file_hash` / source-URL / source-filename / ingest-timestamp
  lineage threaded through every layer. This is provenance and reproducibility,
  not history — current comparison needs it to answer "which file is this price
  from" and to compute freshness.
- `is_current_snapshot` (derived from `valid_from` recency) and the
  `HPT_SILVER_RETENTION_MODE` config (`current_only` default, `all_snapshots`
  opt-in). These are how the current row is *selected*; they remain the seam an
  adopter flips to accumulate history.
- The deterministic cross-snapshot `service_item_id` (decision 0014) and the
  synthetic multi-snapshot validation corpus
  (`scripts/build_multi_snapshot_corpus.py`,
  `slv_audit__service_item_continuity`, the hospital-scope guard test, and
  `docs/development/multi-snapshot-validation.md`). These *prove the identity
  mechanics are correct* without needing real longitudinal data, so they stand
  as a finished artifact rather than open work.

**Do not build (the history deliverable itself):**

- `gld__price_change_history` and any history/change marts, depth, or stability
  metrics.
- Service-item supersession links (`valid_from`/`valid_to` on the service-item
  dimension).
- Over-merge threshold *calibration* against real drift.

Silver Core's "definition of done" no longer waits on any history item beyond
the already-completed identity-mechanics validation. Gold is "finished" at
Phase 1/2 (current comparison + benchmarks); it is not waiting on a history
phase.

## Consequences

- Roadmap Milestone E changes from "the last modeling milestone" to "an
  explicitly out-of-v1-scope extension point." The remaining-modeling
  definition of done (`remaining-steps.md` §7) is met without it.
- The README frames the analytics goal as current cross-hospital comparison and
  lists price-change history under limitations / extension points, not as a
  planned-but-pending feature.
- Decisions 0006 (retention) and 0014 (deterministic identity) remain accepted
  and unchanged in mechanism; their history-oriented rationale is reframed as
  "this is the seam history would build on," and they cross-reference this
  decision.
- The org-adoption goal is preserved by the kept seam plus the
  `proposed-gold-layer-1.md` history design, which remains as a (non-committed)
  reference for an adopter who later accumulates snapshots.
- If history is ever picked up, this decision is the thing to supersede; the
  prerequisites are recorded (orchestrated `all_snapshots` accumulation, then
  supersession + threshold calibration, then the history mart).
