# Hospital Registry Rules

The hospital registry controls which MRF sources the pipeline downloads and how
those sources are identified.

## Active Registry

The active bundled registry is:

```text
src/hpt/registry/hospitals.yml
```

`hpt download` and `hpt ingest` use this bundled file by default through
`src/hpt/registry/loader.py`.

You can override the registry path with:

```bash
hpt download --registry-path path/to/hospitals.yml
hpt ingest --registry-path path/to/hospitals.yml
```

or:

```bash
export HPT_REGISTRY_PATH=path/to/hospitals.yml
```

## Registry Record Contract

Registry records are validated by the Pydantic models in
`src/hpt/registry/models.py`.

Each hospital source should provide:

- A stable `hospital_id`.
- A canonical project hospital name.
- State and other identifying metadata accepted by the model.
- An MRF source URL.
- An expected source format.

The registry should describe publisher sources, not parsed Bronze state.

## Hospital ID Rules

Use hospital IDs as stable pipeline identifiers.

Good IDs are:

- Lowercase.
- Human-readable.
- Stable across source file changes.
- Specific enough to distinguish hospitals in the same system.

Do not use a value that changes with the file, such as a source filename,
download date, or hash.

## Source URL Rules

Source URLs should point to the current hospital-published MRF location when
possible. If a hospital uses an intermediate download endpoint, document any
important behavior in registry notes or a companion issue.

When a URL changes:

- Keep the same `hospital_id` if it represents the same hospital source.
- Update the URL.
- Let snapshot metadata capture the new downloaded file version.

## Expected Format Rules

Expected format is a registry hint. The ingest pipeline still detects and sniffs
the actual downloaded file before selecting a parser.

Use expected format to document what research indicates the hospital publishes,
not to bypass detection.

## Alternate Registry Files

The repository also contains:

```text
registry/hospitals.yaml
registry/hospitals.md
```

These are not the active bundled registry used by the current loader. Treat them
as experimental or historical until the registry strategy is reconciled.

## Future Registry Direction

Likely future work:

- Decide whether the canonical registry should live inside `src/hpt/registry/`
  or in top-level `registry/`.
- Add registry documentation for source research and update workflow.
- Track provenance for each hospital source URL.
- Expand supported states and hospital systems as registry models mature.
- Add tests for any schema migration.
