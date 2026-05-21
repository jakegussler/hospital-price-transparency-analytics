# 0002: Use fsspec Storage Abstraction

Status: accepted

## Context

The project starts as a local-first pipeline, but raw MRF files and snapshot
metadata may eventually move to object storage. Storage logic should not be tied
to local filesystem calls if a small abstraction can avoid that coupling.

## Decision

Use `fsspec` for raw source files and snapshot metadata through
`BronzeStorage`.

## Rationale

`fsspec` supports local files, S3, GCS, and other backends behind a common API.
This lets the pipeline keep local development simple while preserving a path to
cloud storage.

## Consequences

- Raw and metadata paths should be treated as URIs, not only local paths.
- Download and snapshot code should avoid direct `Path` operations for
  `HPT_RAW_STORAGE_BASE_URI` managed paths.
- Tests should continue to cover local `fsspec` behavior.
- Any future cloud migration should be mostly configuration and credential work,
  not a pipeline rewrite.
