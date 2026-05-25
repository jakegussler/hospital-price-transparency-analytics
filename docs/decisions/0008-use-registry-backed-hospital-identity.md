# 0008: Use Registry-Backed Hospital Identity

Status: accepted

## Context

Hospital MRF headers include source-reported names, addresses, NPIs, license
numbers, states, and URLs. These values can vary across files and may not be
stable enough to serve as project identifiers. The pipeline also needs a
controlled list of source URLs to download.

## Decision

Use the bundled hospital registry as the source of project-level hospital
identity and download targets. Treat source-reported hospital fields as observed
MRF metadata, not as the canonical identity contract.

The active bundled registry is `src/hpt/registry/hospitals.yml`, loaded through
`src/hpt/registry/loader.py`.

## Rationale

A registry gives the pipeline stable `hospital_id` values, known source URLs,
expected format hints, and curated hospital metadata. Snapshot metadata can then
record what each file reported without letting file-specific strings redefine the
hospital.

This is especially important for Silver, where historical snapshots and
cross-file analysis require stable hospital joins even when a hospital changes
its published file name, header values, or URL.

## Consequences

- `hospital_id` is the stable project identifier for a hospital source.
- URL changes should update the registry while preserving `hospital_id` when the
  source still represents the same hospital.
- Bronze should preserve source-reported hospital values alongside registry IDs.
- Silver base joins snapshot metadata to the registry-backed hospital dimension.
- Registry expansion and schema changes require validation and tests.
- Alternate files under top-level `registry/` remain experimental until the
  registry strategy is deliberately reconciled.
