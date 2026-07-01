# Methodology

This report covers the current Nashville-metro corpus. Results are corpus-bound
and should not be read as national benchmarks.

Pipeline ownership is deliberately narrow: Python ingests CMS hospital files and
writes source-faithful Bronze; dbt normalizes Silver and Gold; the BI marts
precompute the comparison, trust, denominator, payer matching, and amount-kind
fields; Evidence reads only the exported BI Parquet artifact.

Only direct dollar amounts are price-rankable. Percentages, algorithms, derived
dollar values, and missing amount values are surfaced as context or blockers but
are not mixed into price rankings.

Cross-hospital percentile statistics require at least three reporting hospitals
for the exact service context. Readiness scores measure published-data usability
for this comparison framework, not legal compliance.

Snapshot freshness and source lineage remain visible through `snapshot_id`,
freshness buckets, publication dates, and source URLs in the BI marts.

