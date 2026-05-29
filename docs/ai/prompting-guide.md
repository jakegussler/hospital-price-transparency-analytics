# Prompting Guide

Use these prompt patterns when asking an AI agent to work in this repository.

## Documentation Work

```text
Review README.md, AGENTS.md, and docs/architecture before editing docs.
Preserve the distinction between implemented behavior and planned work.
Update docs/cleanup.md for known mismatches you do not fix.
```

## Parser Work

```text
Review docs/bronze_layer.md, docs/header_parsing.md, and
docs/domain/cms-mrf-schema-notes.md before changing parser behavior.
Keep Bronze source-faithful. Add focused pytest coverage for the format and edge
case being changed.
```

## Download Or Snapshot Work

```text
Review docs/architecture/storage-layout.md and
docs/decisions/0002-use-fsspec-storage-abstraction.md before changing storage or
snapshot behavior. Preserve fsspec compatibility for raw files and metadata.
```

## dbt Work

```text
Review docs/architecture/medallion-layers.md before adding dbt models.
Keep staging close to Bronze, normalize semantics in Silver, and create
analytics-ready outputs in Gold. Add dbt tests for model grain and required
keys.
```

## Payer Mapping Research

```text
Use docs/prompts/payer-plan-mapping-research.md when researching payer and plan
names or updating transform/seeds/canonical_payers.csv,
transform/seeds/payer_aliases.csv, and
transform/seeds/payer_context_rules.csv. Query the local DuckDB data first
when it is available so mappings cover all observed payer plus plan
configurations.
```

## Debugging Work

```text
Start with docs/development/common-debugging-notes.md. Identify whether the
failure is registry, download, snapshot lookup, compression, parser selection,
quarantine, Bronze writing, or dbt external source reading.
```

## Future Cursor Rules

Good future rule candidates:

- Project architecture and medallion boundaries.
- Python parser and storage style.
- HPT domain rules for CMS MRF data.
- dbt/DuckDB modeling conventions.
- Documentation maintenance expectations.

Keep rules short and focused. Use this documentation set as the source of truth
when creating `.cursor/rules/*.mdc` later.
