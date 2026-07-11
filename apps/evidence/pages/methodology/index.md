---
title: Methodology
hide_title: true
sidebar_position: 5
---

# Methodology

Every number on this site is traceable to a hospital's published file. The
comparison rules are public, and rows excluded from comparison carry a reason.
This page summarizes the method; the sub-pages document the rules.

- **[What the price types mean](/methodology/prices)** — list price, cash
  price, negotiated rate, and why they are never ranked against each other.
- **[How comparison works](/methodology/comparability)** — the comparison key,
  the 3-hospital floor, and all 11 blocker reasons.
- **[How scores work](/methodology/scores)** — the data usability score, its
  five components, and the exact band thresholds.

## Where the numbers come from

1. **Hospitals publish** machine-readable standard-charges files, as required
   by federal price transparency rules. Every hospital page links to the
   hospital's own source file.
2. **We ingest and normalize** those files through an open data pipeline:
   structural parsing first, then semantic normalization (code systems, payer
   names, amount classification, service context).
3. **Comparison rules are applied in the data layer, not in this website.**
   The site reads pre-computed, documented tables; it cannot introduce new
   comparisons or reclassify anything. Every rule described here is enforced
   and tested upstream.
4. **This site presents the results** with the comparison status, hospital
   count, and confidence attached to every number.

## The commitments behind every page

- **Corpus-bounded claims.** Every statistic covers only the named corpus
  (currently Nashville metro). Nothing here is a regional or national
  benchmark.
- **One price type at a time.** List prices, cash prices, and insurer
  negotiated rates are never ranked against each other.
- **The 3-hospital floor.** No market statistic is computed from fewer than 3
  hospitals reporting the exact same service context.
- **Blocked, never hidden.** Rows that fail a comparison rule stay visible
  with a named reason. See [data quality](/data-quality).
- **Usability, not compliance.** Hospital scores measure how usable a
  published file is for comparison — they are not legal-compliance findings
  and say nothing about care quality.
- **Traceability.** Every page links to definitions ([glossary](/glossary)),
  the data behind it ([downloads](/downloads)), and the hospital's own source
  file.

## Verifying our work

The full data dictionary and every table this site uses are on the
[downloads page](/downloads), including a build identifier that ties the
published numbers to an exact version of the open-source pipeline. If you
believe a number is wrong, the [about page](/about) explains how to reach us
and what we will check.
