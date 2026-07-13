# Project Documentation

Hospital Price Transparency turns heterogeneous CMS hospital machine-readable
files into source-faithful Parquet, normalized dbt models, and public analytical
outputs. The repository [README](../README.md) is the portfolio overview; this
index is the entry point for technical reviewers and contributors.

## Architecture

- [Pipeline overview](architecture/pipeline-overview.md) — end-to-end flow and
  the boundary between Python parsing, dbt modeling, and public reporting.
- [Medallion layers](architecture/medallion-layers.md) — responsibilities of
  Bronze, Silver, Gold, and the BI presentation layer.
- [Storage layout](architecture/storage-layout.md) — raw files, snapshot
  metadata, Parquet partitions, quarantine output, and DuckDB storage.
- [Bronze schema](architecture/bronze-schema.md) — source-faithful parser output.
- [Silver schema](architecture/silver-schema.md) and [Silver Core](architecture/silver-core.md)
  — normalized foundations and payer/service semantics.
- [Gold schema](architecture/gold-schema.md) — conformed dimensions, the atomic
  rate fact, code bridge, comparison marts, and scorecards.

## Data Methodology

- [HPT glossary](domain/hpt-glossary.md) — project vocabulary.
- [CMS MRF schema notes](domain/cms-mrf-schema-notes.md) — source-format behavior
  and the parser/modeling boundary.
- [CMS validation rules](domain/cms-validation-rules.md) — validation inventory,
  severity, and rejection behavior.
- [Hospital registry rules](domain/hospital-registry-rules.md) — hospital identity
  and source registration requirements.
- [Gold comparability framework](decisions/0017-gold-comparability-framework.md)
  — denominator, context, and rankability rules behind the public analysis.

## Development And Operations

- [Getting started](development/getting-started.md) — installation and the local
  workflow.
- [Runtime configuration](configuration.md) — environment variables and
  precedence.
- [Testing strategy](development/testing-strategy.md) — Python, dbt, and offline
  end-to-end coverage.
- [Snapshot-scoped runs](development/snapshot-scoped-runs.md) — bounded dbt
  execution and recovery.
- [Multi-snapshot validation](development/multi-snapshot-validation.md) —
  continuity checks across hospital snapshots.
- [Common debugging notes](development/common-debugging-notes.md) — recurring
  operational failures and investigation paths.
- [BI presentation layer](development/bi-layer.md) — the public mart contract
  consumed by Evidence.
- [Evidence application guide](../apps/evidence/README.md) — artifact export and
  static-site development.

## Engineering Decisions

The [decision index](decisions/README.md) groups the architectural decision
records by concern. ADRs explain durable tradeoffs; the architecture and
development documents above describe the current implementation.

## AI-Assisted Development

The [AI development guide](ai/README.md) explains how the repository shares one
canonical project contract across Codex, Claude Code, and Cursor without
duplicating context. It also defines when guidance belongs in `AGENTS.md`, a
tool adapter, a project skill, or executable quality checks.

## Documentation Policy

Tracked documentation is reviewer-facing and should describe current behavior.
Local notes, historical research, working prompts, and implementation plans are
retained under ignored paths and are not authoritative.
Unresolved implementation risks remain in [Known Follow-Ups And Risks](cleanup.md)
until they are fixed or moved to an issue tracker.
