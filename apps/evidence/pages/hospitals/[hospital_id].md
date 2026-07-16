```sql hospital
select
  *,
  case data_confidence_band
    when 'high' then 'High'
    when 'moderate' then 'Moderate'
    when 'limited' then 'Limited'
    else 'Low'
  end as data_confidence_label,
  case freshness_bucket
    when '<=90d' then 'within 90 days'
    when '<=180d' then 'within 180 days'
    when '<=365d' then 'within 1 year'
    when '>365d' then 'over 1 year old'
    else 'of unknown age'
  end as file_recency_label
from hpt.hospital_overview
where hospital_id = '${params.hospital_id}'
```

{#if hospital.length === 0}

# Hospital not found

No hospital in the current corpus matches this address.
[Back to the scoreboard.](/hospitals)

{:else}

# {hospital[0].hospital_display_name}

{hospital[0].health_system} · {hospital[0].hospital_type} ·
{hospital[0].canonical_state_name}

<SiteCallout type="scope" title="Where this data comes from">
Based on the standard-charges file this hospital published on
<b><Value data={hospital} column=published_last_updated_on /></b>
({hospital[0].file_recency_label}). You can verify every number against the
hospital's own file: <a href={hospital[0].mrf_url} target="_blank" rel="noopener">source file ↗</a>.
Snapshot: <code>{hospital[0].snapshot_id}</code>.
</SiteCallout>

## Report card

Data confidence: **{hospital[0].data_confidence_label}** — this describes how
usable the published file is for price comparison, not care quality and not
legal compliance. [How scores work.](/methodology/scores)

<Grid cols=3>
  <BigValue data={hospital} value=overall_readiness_score title="Data usability score" fmt=pct0 />
  <BigValue data={hospital} value=freshness_score title="File freshness" fmt=pct0 />
  <BigValue data={hospital} value=code_coverage_score title="Code coverage" fmt=pct0 />
</Grid>
<Grid cols=3>
  <BigValue data={hospital} value=amount_coverage_score title="Dollar-amount coverage" fmt=pct0 />
  <BigValue data={hospital} value=payer_mapping_score title="Insurer-name matching" fmt=pct0 />
  <BigValue data={hospital} value=comparison_readiness_score title="Comparison readiness" fmt=pct0 />
</Grid>

## What this hospital published

<Grid cols=4>
  <BigValue data={hospital} value=charge_item_count title="Charge items" fmt=num0 />
  <BigValue data={hospital} value=observation_count title="Price rows" fmt=num0 />
  <BigValue data={hospital} value=distinct_comparable_codes title="Comparable codes" fmt=num0 />
  <BigValue data={hospital} value=matched_payer_count title="Insurers matched" />
</Grid>

```sql hospital_funnel
select
  stage_index,
  stage_index::int || '. ' || stage_label as stage,
  row_count,
  share_of_published
from hpt.comparability_funnel
where scope_level = 'hospital'
  and hospital_id = '${params.hospital_id}'
order by stage_index
```

Each stage applies one more comparison rule to this hospital's price rows —
what drops out is still visible on this site, just never ranked.
[What the stages mean.](/data-quality)

<BarChart
  data={hospital_funnel}
  x=stage
  y=row_count
  swapXY=true
  sort=false
  yFmt=num0
  title="This hospital's rows surviving each comparison rule"
/>

## Where this hospital stands out

Market position is computed per service context against the corpus-wide
median, only where at least 3 hospitals report the exact context, and always
within one price type.

```sql above_market_count
select count(*) as n
from hpt.hospital_service_rankings
where hospital_id = '${params.hospital_id}'
  and price_position_band in ('high', 'very_high')
```

```sql above_market
select
  service_display_label,
  '/compare/context/' || service_context_url_slug as service_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type,
  comparison_methodology_display_label as methodology,
  hospital_amount,
  market_median_all,
  pct_delta_from_market_median_all,
  peer_hospital_count_all
from hpt.hospital_service_rankings
where hospital_id = '${params.hospital_id}'
  and price_position_band in ('high', 'very_high')
order by pct_delta_from_market_median_all desc
limit 10
```

```sql below_market_count
select count(*) as n
from hpt.hospital_service_rankings
where hospital_id = '${params.hospital_id}'
  and price_position_band in ('low', 'very_low')
```

```sql below_market
select
  service_display_label,
  '/compare/context/' || service_context_url_slug as service_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type,
  comparison_methodology_display_label as methodology,
  hospital_amount,
  market_median_all,
  pct_delta_from_market_median_all,
  peer_hospital_count_all
from hpt.hospital_service_rankings
where hospital_id = '${params.hospital_id}'
  and price_position_band in ('low', 'very_low')
order by pct_delta_from_market_median_all asc
limit 10
```

{#if above_market.length === 0 && below_market.length === 0}

<SiteCallout type="scope" title="No market positions yet">
No service context at this hospital currently meets the 3-hospital comparison
floor, so this export has no above- or below-market positions for the hospital.
Its published prices are browsable through <a href="/compare">Compare Prices</a>
with "Everything published" selected.
</SiteCallout>

{:else}

### Priced above the area market

Showing the top {above_market.length} of {(above_market_count[0]?.n ?? 0).toLocaleString()} contexts priced 10%+ above the area median.

<DataTable data={above_market} link=service_link>
  <Column id=service_display_label title="Service" />
  <Column id=price_type title="Price type" />
  <Column id=methodology title="Methodology" />
  <Column id=hospital_amount title="This hospital" fmt=usd0 />
  <Column id=market_median_all title="Area median" fmt=usd0 />
  <Column id=pct_delta_from_market_median_all title="vs. median" fmt=pct0 />
  <Column id=peer_hospital_count_all title="Peers (n)" />
</DataTable>

### Priced below the area market

Showing the top {below_market.length} of {(below_market_count[0]?.n ?? 0).toLocaleString()} contexts priced 10%+ below the area median.

<DataTable data={below_market} link=service_link>
  <Column id=service_display_label title="Service" />
  <Column id=price_type title="Price type" />
  <Column id=methodology title="Methodology" />
  <Column id=hospital_amount title="This hospital" fmt=usd0 />
  <Column id=market_median_all title="Area median" fmt=usd0 />
  <Column id=pct_delta_from_market_median_all title="vs. median" fmt=pct0 />
  <Column id=peer_hospital_count_all title="Peers (n)" />
</DataTable>

{/if}

## Insurer rates vs. this hospital's cash price

Comparing a negotiated rate to the same hospital's cash price needs no
cross-hospital floor — both numbers come from this one hospital's file. The
comparison is only made where it is meaningful: a per-diem rate is a DAILY
amount and is never labeled above or below a cash price.

```sql cash_bands
select
  case cash_comparison_band
    when 'below_cash' then 'Negotiated below cash price'
    when 'equal_to_cash' then 'Same as cash price'
    when 'above_cash' then 'Negotiated ABOVE cash price'
    when 'cash_unavailable' then 'No cash price published'
    when 'per_diem_incompatible' then 'Per-diem (daily) rate — not comparable to cash'
    when 'ambiguous_negotiated_context' then 'Contract has mixed amounts — excluded'
  end as comparison,
  count(*) as context_count
from hpt.payer_contracting_explorer
where hospital_id = '${params.hospital_id}'
group by cash_comparison_band
order by
  case cash_comparison_band
    when 'below_cash' then 1
    when 'equal_to_cash' then 2
    when 'above_cash' then 3
    when 'cash_unavailable' then 4
    when 'per_diem_incompatible' then 5
    else 6
  end
```

{#if cash_bands.length === 0}

<SiteCallout type="scope">
No matched-insurer negotiated rates are available for this hospital.
</SiteCallout>

{:else}

<DataTable data={cash_bands}>
  <Column id=comparison title="Negotiated rate vs. cash price" />
  <Column id=context_count title="Contexts" fmt=num0 />
</DataTable>

```sql above_cash_examples_count
select count(*) as n
from hpt.payer_contracting_explorer
where hospital_id = '${params.hospital_id}'
  and cash_comparison_band = 'above_cash'
```

```sql above_cash_examples
select
  payer_display_name,
  service_display_label,
  '/compare/context/' || service_context_url_slug as service_link,
  comparison_methodology_display_label as methodology,
  negotiated_dollar,
  hospital_cash_amount,
  pct_delta_from_hospital_cash
from hpt.payer_contracting_explorer
where hospital_id = '${params.hospital_id}'
  and cash_comparison_band = 'above_cash'
order by pct_delta_from_hospital_cash desc
limit 15
```

{#if above_cash_examples.length > 0}

### Where insurers pay more than cash

Showing the top {above_cash_examples.length} of {(above_cash_examples_count[0]?.n ?? 0).toLocaleString()} contexts where a negotiated rate exceeds this hospital's own cash price.

<SiteCallout type="caution">
A negotiated rate above the cash price is a signal to investigate, not proof
of overpayment — bundles, units, and plan contexts can differ between the two
published numbers. <a href="/methodology/prices#negotiated-vs-cash">How to read this comparison.</a>
</SiteCallout>

<DataTable data={above_cash_examples} link=service_link>
  <Column id=payer_display_name title="Insurer" />
  <Column id=service_display_label title="Service" />
  <Column id=methodology title="Methodology" />
  <Column id=negotiated_dollar title="Negotiated rate" fmt=usd0 />
  <Column id=hospital_cash_amount title="Cash price" fmt=usd0 />
  <Column id=pct_delta_from_hospital_cash title="Above cash by" fmt=pct0 />
</DataTable>

{/if}

{/if}

## Why some of this hospital's rows can't be compared

A single row can carry several blockers at once, so counts overlap.
[Full blocker explanations.](/data-quality)

```sql hospital_blockers
select
  blocker_label,
  case blocker_category
    when 'snapshot_freshness' then 'Outdated file version'
    when 'code_comparability' then 'Billing code not comparable'
    when 'amount_semantics' then 'Not a rankable dollar price'
    when 'service_context' then 'Service context must stay separate'
    when 'payer_identity' then 'Insurer name not identified'
    when 'payer_context' then 'Insurance market type unknown'
  end as blocker_group,
  blocked_row_count,
  blocked_row_share
from hpt.comparison_blocker_summary
where hospital_id = '${params.hospital_id}'
order by blocked_row_count desc
```

<DataTable data={hospital_blockers}>
  <Column id=blocker_label title="Reason" />
  <Column id=blocker_group title="Group" />
  <Column id=blocked_row_count title="Rows affected" fmt=num0 />
  <Column id=blocked_row_share title="Share of rows" fmt=pct1 />
</DataTable>

<SiteCallout type="caution" title="Reading this page fairly">
Everything above describes the hospital's published data file under this
project's comparison framework. It is not a legal-compliance finding, not a
statement about care quality, and prices shown are not a patient's
out-of-pocket cost.
</SiteCallout>

{/if}
