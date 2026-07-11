---
title: Overview
hide_title: true
---

# Nashville Hospital Price Transparency

Hospitals are required to publish their standard charges. This site organizes
those files for Nashville-area hospitals and explains when the published prices
**can and cannot be compared** across hospitals.

```sql export_metadata
select
  left(max(exported_at_utc), 10) as exported_on,
  max(corpus_label) as corpus_label,
  max(build_id) as build_id
from hpt.public_metadata
```

```sql market
select
  *,
  (meets_floor_row_count = 0) as no_floor_met
from hpt.market_summary
```

<SiteCallout type="scope">
Covers the <b><Value data={export_metadata} column=corpus_label /></b> corpus:
<Value data={market} column=hospital_count /> hospitals across
<Value data={market} column=health_system_count /> health systems, using each
hospital's current published file (published between
<Value data={market} column=earliest_published_last_updated_on /> and
<Value data={market} column=latest_published_last_updated_on />).
Data exported <Value data={export_metadata} column=exported_on />.
Results describe this corpus only — they are not regional or national benchmarks.
</SiteCallout>

## The market at a glance

<Grid cols=4>
  <BigValue data={market} value=hospital_count title="Hospitals" />
  <BigValue data={market} value=distinct_service_count title="Services published" fmt=num0 />
  <BigValue data={market} value=distinct_comparable_service_count title="Services comparable across hospitals" fmt=num0 />
  <BigValue data={market} value=matched_payer_count title="Insurers identified" />
</Grid>

<Details title="How to read this site (start here)">

Every price on this site carries three facts: **what kind of price it is**,
**how many hospitals it is compared against** (the "n"), and **whether it
qualifies for comparison** under our rules.

Hospitals publish three kinds of prices, and we never rank one kind against
another:

- **List price** (gross charge) — the chargemaster amount, which almost no one
  pays directly.
- **Cash price** (discounted cash) — the self-pay amount.
- **Negotiated rate** — the amount agreed with a specific insurer.

We only compute market statistics (medians, percentiles, rankings) for a
service context reported by **at least 3 hospitals**. Anything below that floor
stays visible but is labeled "too few hospitals to compare" instead of being
silently dropped. Details are in the [methodology](/methodology).

</Details>

## From published to comparable

Hospitals publish far more price rows than qualify for cross-hospital
comparison. Each stage below applies another comparison rule. Rows that do not
pass remain in the data but are excluded from rankings.

```sql corpus_funnel
select
  stage_index,
  stage_index::int || '. ' || stage_label as stage,
  row_count,
  share_of_published
from hpt.comparability_funnel
where scope_level = 'corpus'
order by stage_index
```

<BarChart
  data={corpus_funnel}
  x=stage
  y=row_count
  swapXY=true
  sort=false
  yFmt=num0
  title="Price rows surviving each comparison rule"
/>

<DataTable data={corpus_funnel}>
  <Column id=stage title="Stage" />
  <Column id=row_count title="Price rows" fmt=num0 />
  <Column id=share_of_published title="Share of published" fmt=pct1 />
</DataTable>

{#if market.length > 0 && market[0].no_floor_met}

<SiteCallout type="caution" title="No cross-hospital comparisons in this export">
No service context in this export is reported by 3 or more hospitals in exactly
the same form, so the site cannot publish market statistics. The hospitals'
published prices are still browsable, and
within-hospital comparisons (like negotiated rate vs. cash price) do not need
the floor. See <a href="/data-quality">why comparisons are limited</a>.
</SiteCallout>

{/if}

## Hospitals by data confidence

Data confidence describes how usable each hospital's **published file** is for
price comparison. It does not measure care quality or legal compliance.

```sql confidence_bands
select
  case data_confidence_band
    when 'high' then 'High'
    when 'moderate' then 'Moderate'
    when 'limited' then 'Limited'
    else 'Low'
  end as confidence,
  count(*) as hospital_count
from hpt.hospital_overview
group by data_confidence_band
order by
  case data_confidence_band
    when 'high' then 1
    when 'moderate' then 2
    when 'limited' then 3
    else 4
  end
```

<DataTable data={confidence_bands}>
  <Column id=confidence title="Data confidence" />
  <Column id=hospital_count title="Hospitals" />
</DataTable>

See the [hospital scoreboard](/hospitals) for each hospital's score and what it
is made of.

## Featured price comparisons

```sql featured
select
  featured_rank,
  service_display_label,
  '/compare/' || service_url_slug as service_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type,
  hospital_count,
  median_amount,
  p10_amount,
  p90_amount,
  spread_ratio_p90_to_p10
from hpt.featured_services
order by featured_rank
```

{#if featured.length === 0}

<SiteCallout type="scope" title="Nothing featured yet">
Featured comparisons appear when a described service is reported by at least 3
hospitals in the same context. None qualify in this export. You can still
<a href="/compare">browse everything hospitals published</a>.
</SiteCallout>

{:else}

Each row shows its hospital count ("n") — the number of hospitals behind the
statistics. Click a service to see every hospital's price.

<DataTable data={featured} link=service_link search=true>
  <Column id=service_display_label title="Service" />
  <Column id=price_type title="Price type" />
  <Column id=hospital_count title="Hospitals (n)" />
  <Column id=median_amount title="Typical (median)" fmt=usd0 />
  <Column id=p10_amount title="Lower (10th pct)" fmt=usd0 />
  <Column id=p90_amount title="Upper (90th pct)" fmt=usd0 />
  <Column id=spread_ratio_p90_to_p10 title="Price spread (x)" fmt=num1 />
</DataTable>

{/if}

## Why many rows can't be compared

```sql blocker_categories
select
  case blocker_category
    when 'snapshot_freshness' then 'Outdated file version'
    when 'code_comparability' then 'Billing code not comparable'
    when 'amount_semantics' then 'Not a rankable dollar price'
    when 'service_context' then 'Service context must stay separate'
    when 'payer_identity' then 'Insurer name not identified'
    when 'payer_context' then 'Insurance market type unknown'
  end as blocker_group,
  sum(blocked_row_count) as blocked_row_count
from hpt.comparison_blocker_summary
group by blocker_category
order by blocked_row_count desc
```

A single row can be blocked for several reasons at once, so these counts
overlap. The full explanation of every blocker lives on the
[data quality page](/data-quality).

<BarChart
  data={blocker_categories}
  x=blocker_group
  y=blocked_row_count
  swapXY=true
  yFmt=num0
  title="Price rows blocked from strict comparison, by reason group"
/>

---

<SiteCallout type="caution" title="What this site is not">
These are hospital-published standard charges — not quotes, and not your
out-of-pocket cost. Scores describe published-data usability, not legal
compliance and not quality of care. Every claim is bounded to the corpus named
at the top of this page.
</SiteCallout>

Questions about how a number is computed? Start with the
[methodology](/methodology) or the [glossary](/glossary). Want the data
itself? See [downloads](/downloads).
