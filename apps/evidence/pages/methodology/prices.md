---
title: What the price types mean
hide_title: true
sidebar_position: 1
---

# What the Price Types Mean

Hospitals publish several kinds of "price" for the same service. Each answers a
different question, so this site analyzes them separately.

## The three rankable price types

### List price (gross charge)

The hospital's full chargemaster amount — the "sticker price." Almost no one
pays it directly, but it anchors percentage-based contracts and uninsured
billing. Useful for spotting extreme variation; a poor guide to what anyone
actually pays.

### Cash price (discounted cash)

The amount for patients paying without insurance. Usually lower than the list
price, and sometimes lower than insurers' negotiated rates — which is why we
compare the two directly ([see below](#negotiated-vs-cash)).

### Negotiated rate (negotiated dollar)

The dollar amount a specific insurer agreed to pay the hospital for the
service. Each insurer-hospital pair can have its own rate, and one hospital
can publish many rates for one service. On hospital and service pages, a
hospital's "price" for a context is ONE representative amount: each insurer
contract's rate counts once (a rate repeated across many rows — for example
against dozens of revenue-code variants — is deduplicated first), and the
hospital's representative is the median across its contracts. Each insurer's
rate is also individually visible in the insurer views.

## Payment methodology: what unit the rate buys

A negotiated dollar is only meaningful together with **how** it is paid. CMS
files label each rate with a methodology, and we never mix methodologies in
one comparison:

- **Fee schedule (per item/service)** — the amount applies to one item or
  service. The most directly comparable kind of rate.
- **Case rate (per episode)** — one flat amount covers an entire episode or
  bundle of care, however long it takes.
- **Per diem (per day)** — the amount is **per day** of inpatient care. A
  $1,947 per-diem is a daily payment, NOT the price of a full stay — comparing
  it against a $160,000 case rate would be meaningless, so we never do.

Every negotiated-rate comparison on this site is methodology-specific: a
per-diem cohort contains only per-diem rates, a case-rate cohort only case
rates. Per-diem rates are also never labeled above or below a cash price,
because the cash price describes an item or episode, not a day.

## Market statistics are hospital-weighted

Every market median and percentile is computed over one representative price
per hospital — one hospital, one vote. Raw row counts are shown for
transparency, but a hospital repeating one rate hundreds of times gains no
statistical weight. Insurer contracts whose rows carry several different
amounts for the exact same context are excluded from statistics and labeled
in [data quality](/data-quality), never silently averaged.

## Published values that are never ranked as prices

Hospitals also publish amounts that are **not** directly rankable dollar
prices. We show them as context and count them in
[data quality](/data-quality), but they never enter price rankings:

- **Percentages** — "45% of billed charges" depends on the (unranked) charge.
- **Algorithms** — a textual formula, not a number.
- **Estimates** — estimated allowed amounts, not agreed prices.
- **Derived dollars** — dollar figures we could compute from a percentage or
  formula. We deliberately do not mix calculated numbers with directly quoted
  ones.
- **Statistical fields** — published minimums, maximums, medians, or
  percentiles of other rates describe distributions, not a specific agreed
  price.

## Negotiated vs cash

When a hospital publishes both a cash price and an insurer's negotiated rate
for the same charge-item context, we compare the two. This is a
**within-hospital** comparison: both numbers come from one hospital's file, so
it does not need the [3-hospital floor](/methodology/comparability#the-3-hospital-floor).

Sometimes the negotiated rate is **above** the cash price — a finding worth
attention, since it suggests an insured patient's plan pays more than a
walk-in would. Read it carefully:

- The two published numbers can cover slightly different bundles or units.
- Plan context differs — a negotiated rate may include obligations the cash
  price does not.
- We compare only directly published dollar amounts (derived dollars are
  excluded), but hospital files vary in how they define each field.

We publish the comparison with the exact counts and label it a **signal to
investigate, not proof of overpayment**.

## What none of these numbers are

Published standard charges are not quotes and not your expected bill.
Deductibles, coinsurance, out-of-network rules, and bundling mean a patient's
out-of-pocket cost can differ greatly from every number on this site. Use
these pages to understand price structure and variation — not to predict a
specific bill.
