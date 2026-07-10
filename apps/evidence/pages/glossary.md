---
title: Glossary
hide_title: true
sidebar_position: 6
---

# Glossary

Every term and label used on this site, in plain language. Deeper explanations
live in the [methodology](/methodology).

## Prices

### List price

The hospital's full chargemaster amount (published as "gross charge"). Almost
no one pays it directly.

### Cash price

The amount for patients paying without insurance (published as "discounted
cash").

### Negotiated rate

The dollar amount a specific insurer agreed to pay the hospital for a service
(published as "negotiated dollar"). One hospital can have many negotiated
rates for one service — one per insurer contract.

### Price row / observation

One published amount in a hospital's file: one source row and one price type.
A single charge item usually produces several price rows (its list price, cash
price, and each insurer's rate).

### Derived dollar

A dollar figure calculated from a published percentage or formula rather than
directly quoted. Shown as context, never ranked against quoted prices.

## Services and contexts

### Service context

The exact combination prices are compared within: billing code + care setting
+ billing type + modifier set (+ drug units) + price type. If any part
differs, prices are never mixed. See
[how comparison works](/methodology/comparability).

### Billing code

A standardized identifier for a service. Code systems used here include
MS-DRG (inpatient stays), CPT (procedures), HCPCS (procedures/supplies), and
APC (outpatient payment groups). Internal chargemaster codes ("CDM") are not
comparable across hospitals.

### Care setting

Whether the price covers inpatient or outpatient care. "Not specified" means
the hospital's file did not say.

### Billing type

Whether the price covers the facility fee or the professional (clinician) fee.
"Not labeled by hospital" means the file omitted it; such rows are only ever
compared with other unlabeled rows.

### Modifiers

Billing codes' add-on flags that change what is being priced — for example
professional-only (26) or technical-only (TC) components. Rows with different
modifier sets are never merged.

### Description not available

The service's code has no displayable description. For CPT/CDT codes this is a
licensing constraint (AMA-licensed descriptions cannot be republished); for
other systems the public-domain reference data is not yet loaded. The code
itself still compares correctly.

## Comparison vocabulary

### Hospitals (n)

The number of hospitals reporting the exact service context — the denominator
behind every market statistic. Shown next to every comparison on this site.

### The 3-hospital floor

No market statistic is computed from fewer than 3 hospitals reporting the
exact same context. Below the floor, individual prices stay visible but the
context is labeled "Too few hospitals."
[Why.](/methodology/comparability#the-3-hospital-floor)

### Comparison status

Whether a service context qualifies for cross-hospital comparison:
**Comparable (described)** — comparable with a service description;
**Comparable (code only)** — comparable by billing code, description
unavailable; **Too few hospitals** — below the 3-hospital floor.

### Comparison confidence

How solid a context's comparison is: **High** (10+ hospitals, described),
**Moderate** (5–9), **Limited** (3–4), **Low** (below the floor).
[Details.](/methodology/scores)

### Typical (median)

The middle value: half of hospitals price above it, half below. More robust
than an average against extreme values.

### Lower / Upper (10th / 90th percentile)

The price below which 10% (or 90%) of the context's prices fall. At small n
these are close to the minimum and maximum — that is why they only appear
above the floor.

### Price spread (×)

The 90th-percentile price divided by the 10th-percentile price. A spread of
4× means the high end is four times the low end.

### Variation band

How spread out a context's prices are: **very high variation** (spread ≥ 3×),
**high variation** (≥ 2×), **moderate variation**, or **not ranked** (below
the floor).

### Market position

Where one hospital's price sits vs. the corpus median for one exact context:
well below / below / near / above / well above market, using ±10% and ±25%
thresholds. [Details.](/methodology/scores)

### Blocker

A named, stable reason a row or context is excluded from stricter comparison —
never an undocumented filter. All 11 are explained on the
[data quality page](/data-quality).

## Hospitals and files

### Data usability score

A hospital's 0–100% score for how usable its published file is for price
comparison: the average of freshness, code coverage, dollar-amount coverage,
insurer-name matching, and comparison readiness. **Not a legal-compliance
finding.** [Details.](/methodology/scores)

### Data confidence

The usability score as a band: High (≥85%), Moderate (≥70%), Limited (≥50%),
Low. Describes the published file, not the hospital's care.

### File recency

How recently the hospital's file says it was updated: within 90 days / 180
days / 1 year / over a year old.

### Snapshot

One captured version of a hospital's published file, identified by a snapshot
id. Only each hospital's current snapshot feeds comparisons.

### Source file

The hospital's own machine-readable standard-charges file. Every hospital page
links to it so any number can be checked against the primary source.

## Insurers

### Matched insurer

A published payer name that the pipeline confidently matched to a canonical
insurer identity (e.g. "BCBS TN" → BlueCross BlueShield of Tennessee). Only
matched rates appear in insurer views.

### Insurer market median

For one insurer and one service context: the median of that insurer's
negotiated rates across hospitals (needs the 3-hospital floor).

### Rates above cash price

Contexts where an insurer's negotiated rate exceeds the hospital's own cash
price. A signal to investigate, not proof of overpayment.
[How to read it.](/methodology/prices#negotiated-vs-cash)

## Site-wide

### Corpus

The set of hospitals currently loaded — named on every page (currently
Nashville metro). Every claim on the site is bounded to it.

### Comparability funnel

The count of price rows surviving each comparison rule, from "published" down
to "meets the 3-hospital floor." Shown for the whole corpus and per hospital.
[See it.](/data-quality)

### Build identifier

The exact version of the open-source pipeline that produced the published
data, shown on the [downloads page](/downloads) for citability.
