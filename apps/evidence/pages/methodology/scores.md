---
title: How scores work
hide_title: true
sidebar_position: 3
---

# How Scores Work

The site uses two different confidence measures. They answer different
questions and are deliberately named differently:

- **Data confidence** (per hospital) — how usable is this hospital's published
  file?
- **Comparison confidence** (per service context) — how solid is this
  cross-hospital comparison?

Neither is a legal-compliance finding, and neither says anything about quality
of care.

## Data usability score (per hospital)

Each hospital gets a 0–100% usability score: the simple average of five
component scores, each 0–100%.

| Component | What it measures |
|---|---|
| File freshness | How recently the file says it was updated: within 90 days = 100%, within 180 days = 75%, within 1 year = 50%, older = 25%. |
| Code coverage | Share of the hospital's charge items carrying a billing code usable across hospitals. |
| Dollar-amount coverage | Share of price rows published as dollar amounts rather than percentages or formulas. |
| Insurer-name matching | Share of payer rates whose insurer name we could match to a canonical insurer. |
| Comparison readiness | Share of classified rows with full service context (specific code, setting, and billing type). |

**Data confidence bands** come straight from the overall score:

| Band | Threshold |
|---|---|
| High | 85% and above |
| Moderate | 70% – 84% |
| Limited | 50% – 69% |
| Low | below 50% |

Read the score as "how much of this file can honest comparison actually use."
A low score often reflects file format or labeling choices — for example,
publishing percentages instead of dollars, or omitting billing types.

## Comparison confidence (per service context)

Set by cohort size and description availability:

| Band | Rule |
|---|---|
| High | 10+ hospitals report the context and the service has a description |
| Moderate | 5–9 hospitals |
| Limited | 3–4 hospitals (meets the floor, but barely) |
| Low | below the 3-hospital floor — no market statistics published |

## Market position bands (per hospital, per service context)

Where a hospital's price sits against the corpus median for one exact context,
published only above the 3-hospital floor:

| Band | Rule |
|---|---|
| Well below market | 25%+ below the median, or bottom decile |
| Below market | 10–25% below the median, or bottom quartile |
| Near market | within 10% of the median |
| Above market | 10–25% above the median, or top quartile |
| Well above market | 25%+ above the median, or top decile |

The same ±10% / ±25% thresholds apply to insurer-market positions (a
negotiated rate vs. the same insurer's median across hospitals).

**Variation bands** describe a whole context's spread: "very high variation"
means the 90th-percentile price is at least 3× the 10th-percentile price;
"high variation" means at least 2×.

## Why we publish the thresholds

Bands without thresholds are vibes. Every cutoff above is the actual value in
the open-source data layer, locked by automated tests — if a threshold ever
changes, this page changes with it (the build identifier on the
[downloads page](/downloads) ties the two together).

## What the scores are not

- Not legal-compliance findings — we do not assess conformance with federal
  requirements, only practical usability for comparison.
- Not care-quality measures.
- Not price levels — a hospital can publish superbly usable data and have high
  prices, or vice versa.
- Not precise to the decimal — treat small score differences between hospitals
  as noise; the bands matter more than the ranks.
