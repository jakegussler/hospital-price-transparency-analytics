# 0019: Scope The Active Corpus And Enrich Code Descriptions

Status: accepted

## Context

The pipeline is correct but its analytical output was not yet demonstrable. Two
gaps blocked a credible work-in-progress portfolio README:

1. **Denominator floor vs. a scattered corpus.** Gold gates every cross-hospital
   percentile/benchmark at a 3-hospital floor (decision 0017). The loaded corpus
   was a geographic grab-bag (CA, GA, ID, IL, MI, MN, WI, scattered TN), so very
   few service codes had ≥3 *comparable* reporters and almost every cross-hospital
   cut was suppressed. Breadth of geography actively hurt comparability: hospitals
   in different markets rarely share code systems or service lines.
2. **Illegible marts.** Marts are keyed by `service_code_key`
   (`md5(canonical_code_system || match_code)`). Without code descriptions, a
   reader can only navigate by memorized codes; there was no way to find a service
   by a human-readable attribute.

The registry also had no way to scope the working set: `load_registry` returned
every entry, so the only way to narrow the corpus was to delete research.

## Decision

Three coordinated changes, scoped as a deliberate small-sample placeholder while
infrastructure and corpus breadth are built out — **not** as a pivot to a
single-metro product.

1. **Registry activation flag.** `HospitalSource` gains `active: bool = True`.
   `load_registry(include_inactive=False)` returns only active hospitals — the
   working set for bulk download/ingest, the dbt `hospitals` seed export, and the
   all-hospitals dbt resolution. `get_hospital(s)` still resolve inactive
   hospitals by explicit id, and validation/duplicate checks always span the full
   file. Deactivation retains URL research instead of deleting it.

2. **Active corpus = Nashville, TN metro.** Scope the active set to the
   Nashville–Davidson–Murfreesboro–Franklin MSA: Vanderbilt (VUMC + Wilson
   County), the nine HCA TriStar division hospitals, and independents (Williamson
   Medical Center, Metro Nashville General, Maury Regional). This maximizes the
   fraction of codes clearing the 3-hospital floor (the nine TriStar hospitals
   share code systems and methodology), gives a within-system *and* between-system
   contrast, and spans all three MRF formats (JSON, CSV wide, CSV tall). MRF URLs
   were discovered from each system's CMS-mandated `cms-hpt.txt`.

3. **Green-light code-description enrichment.** Build the reference-loader pattern
   from `docs/local/external-data-enrichment.md`, starting with the smallest,
   highest-signal public-domain source: **CMS MS-DRG** (IPPS Final Rule Table 5).
   `hpt load-reference` downloads, parses, and writes the release to
   `{HPT_REFERENCE_ROOT}/{table}/release_date=.../*.parquet` with full provenance
   (`code_edition`, `source_url`, `retrieved_at`). dbt exposes it via the
   `reference` source, normalizes it in `slv_core__billing_code_descriptions` to
   the `(canonical_code_system, match_code)` keys Silver already produces, and
   `gld_dim__service_code` left-joins it at the seam decision 0017 reserved —
   adding `code_description` and grouper context without reshaping the marts.

## Consequences

- The active corpus is intentionally small and regional. Cross-hospital figures
  are illustrative of what the pipeline produces, not a market study; the README
  and scorecards must state the denominator and the 3-hospital floor.
- `gld_dim__service_code` is no longer thin: it carries descriptions for
  green-light systems. Licensed systems (CPT, CDT, 3M DRGs) stay
  `code_description` null with a license marker until a license is acquired;
  `has_code_description` gates the legible subset without filtering the dimension.
- The conformed dimension carries the **latest** loaded edition's description per
  code rather than a per-snapshot as-of join — a documented v1 simplification,
  acceptable while every active MRF is the same vintage. Per-snapshot as-of
  alignment remains the future step (enrichment doc Phase 3).
- Reference data is **not** committed: it is downloaded on demand by
  `hpt load-reference` and written under git-ignored `data/reference/`.
- Reactivating or adding hospitals is now a one-line `active:` flip / new entry;
  the deactivated multi-state research is preserved for later expansion.

See `docs/local/external-data-enrichment.md` (source backlog) and
`src/hpt/reference/` (loader).
