---
title: How comparison works
hide_title: true
sidebar_position: 2
---

# How Comparison Works

Two hospital prices are comparable only if they describe the same service and
payment context. This page lists the rules enforced and tested in the
open-source data layer that supplies the site.

## The comparison key

Prices are compared across hospitals only within an exact **service context**,
which is the combination of all of these:

- billing code system + code
- care setting (inpatient / outpatient)
- billing type (facility / professional)
- billing modifier set
- drug unit context (for drug codes)
- price type (list / cash / negotiated)
- payment methodology (for negotiated rates: fee schedule / case rate /
  per diem — a per-diem is a DAILY amount and never mixes with episode or
  item prices)

If any part differs, the rows land in different contexts and are never mixed.
Every exact context has a stable address of its own
(`/compare/context/…`), so links from hospital and insurer pages always land
on the precise comparison they came from. Three consequences worth knowing:

- **The same code appears multiple times.** A knee MRI billed in an outpatient
  facility context is a different row from the same code billed
  professionally. Service pages show all contexts side by side.
- **"Not labeled by hospital"** is a real context. When a hospital omits the
  billing type, we keep those rows in their own "unspecified" bucket rather
  than guessing — they only ever compare against other unlabeled rows.
- **Modifier rows stay separate.** Modifiers like professional-only (26) or
  technical-only (TC) change what is being priced; we never blend them with
  unmodified rows.

## Which codes can compare at all

Standard code systems (MS-DRG, CPT, HCPCS, APC, …) mean the same thing at
every hospital, so they can anchor comparison. Internal chargemaster codes and
local codes cannot — they stay visible but blocked. Codes must also be
**specific** enough to identify one service; broad catch-all codes are blocked
from ranking.

A note on descriptions: MS-DRG descriptions are public domain and shown.
CPT/CDT descriptions are licensed by the AMA and **cannot be republished
here** — those services show "Description not available" with the code still
fully comparable. This is a licensing constraint, not a hospital failure, and
the site says so wherever it appears.

## One hospital, one vote

Every market statistic is computed **hierarchically** so that repetition in a
published file can never add statistical weight:

1. Rows repeating one amount under one insurer contract collapse to a single
   contract amount. (One hospital published a single per-diem rate against 56
   revenue-code variants of one MS-DRG; it counts once.)
2. A hospital's representative price for a context is the median of its
   contract amounts.
3. Market medians and percentiles are computed over those hospital
   representatives — one per hospital.

A contract whose rows carry several **different** amounts for the exact same
context hides a distinction the file does not label. We exclude it from
statistics rather than average it, and service pages show how many hospitals
were excluded this way.

## The 3-hospital floor

No market statistic — median, percentile, spread, ranking, or "vs. market"
position — is computed unless **at least 3 hospitals** have a safely
representable price for the exact same service context.

With 2 hospitals, a median is only the halfway point between two prices, and a
range simply reports those two values. Even at n=3, a 10th or 90th percentile
is close to the minimum or maximum. Below the floor, we show the individual
prices and the hospital count and label the context "Too few hospitals."

The floor applies separately to every peer group: the all-corpus market, the
same-state group, the same-hospital-type group, the same-health-system group,
and each insurer's cross-hospital market.

## Insurer (payer) matching

Hospitals write insurer names free-form — "BCBS", "Blue Cross TN", "BCBST"
can all be one insurer. The pipeline matches published names to canonical
insurer identities using documented rules. Only matched rates enter insurer
views; unmatched names are counted openly as the "Insurer name couldn't be
identified" blocker. Matching coverage per hospital is published as the
insurer-name matching score.

## Currentness

Only each hospital's **current** file feeds comparisons. Every hospital page
shows the file's own published date, its recency bucket, and a link to the
source file. Superseded files are blocked with the "outdated file version"
reason.

## The 12 blocker reasons

Every exclusion from a stricter comparison is one of 12 named, stable reasons
— never an undocumented filter. Ten apply per row; two apply at a wider grain
(the 3-hospital floor per service context, and mixed-amount contracts per
insurer contract). The full plain-language catalog, with counts for the
current corpus, lives on the [data quality page](/data-quality).

## What we deliberately do not do

- No fuzzy matching of service descriptions across hospitals — descriptions
  can look alike while covering different things.
- No cross-unit drug conversions.
- No mixing of price types, ever.
- No mixing of payment methodologies, ever — and no converting a per-diem
  into an episode price.
- No derived-dollar rankings.
- No observation-weighted statistics — one hospital, one vote.
- No claims beyond the loaded corpus.

These rules reduce coverage in exchange for more consistent comparisons. The
[data quality page](/data-quality) reports their effect on the published rows.
