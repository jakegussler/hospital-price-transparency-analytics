```sql context_header
select
  service_display_label,
  service_display_code,
  canonical_code_system,
  match_code,
  description_availability,
  service_url_slug,
  '/compare/' || service_url_slug as service_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type_label,
  comparison_methodology,
  comparison_methodology_display_label,
  case comparison_methodology
    when 'fee schedule' then 'Fee schedule: each negotiated amount applies per item or service.'
    when 'case rate' then 'Case rate: each negotiated amount covers an entire episode or bundle of care.'
    when 'per diem' then 'Per diem: each negotiated amount is PER DAY of inpatient care. It is not the price of a full stay, and it is never compared with case rates or fee schedules.'
    else ''
  end as methodology_note,
  case clean_setting
    when 'unspecified' then 'Not specified'
    else clean_setting
  end as setting,
  case clean_billing_class
    when 'unspecified' then 'Not labeled by hospital'
    else clean_billing_class
  end as billing_type,
  modifier_display_label,
  canonical_drug_unit_type,
  hospital_count,
  reporting_hospital_count::double as reporting_hospital_count,
  excluded_hospital_count::double as excluded_hospital_count,
  contract_count::double as contract_count,
  observation_count,
  payer_count,
  meets_hospital_threshold,
  case comparison_status
    when 'insufficient_denominator' then 'Too few hospitals'
    when 'described_comparable' then 'Comparable (described)'
    when 'code_only_comparable' then 'Comparable (code only)'
  end as comparison,
  case comparison_confidence_band
    when 'high' then 'High'
    when 'moderate' then 'Moderate'
    when 'limited' then 'Limited'
    else 'Low'
  end as confidence,
  median_amount,
  p10_amount,
  p90_amount,
  spread_ratio_p90_to_p10
from hpt.service_market_explorer
where service_context_url_slug = '${params.service_context_url_slug}'
limit 1
```

{#if context_header.length === 0}

# Context not found

No published data matches this exact-context address. It may have left the
corpus in a data refresh, or fallen below the comparison floor.
[Browse all services](/compare).

{:else}

# {context_header[0].service_display_label}

**Billing code:** {context_header[0].service_display_code} ·
**Price type:** {context_header[0].price_type_label} ·
**Methodology:** {context_header[0].comparison_methodology_display_label} ·
**Care setting:** {context_header[0].setting} ·
**Billing type:** {context_header[0].billing_type} ·
**Modifiers:** {context_header[0].modifier_display_label}

This page shows ONE exact comparison context. Prices here are only ever
compared with prices published under the same price type, payment
methodology, care setting, billing type, and modifiers.
<a href={context_header[0].service_link}>All contexts for this service</a>.

{#if context_header[0].methodology_note !== ''}

<SiteCallout type="definition" title={context_header[0].comparison_methodology_display_label}>
{context_header[0].methodology_note}
</SiteCallout>

{/if}

{#if !context_header[0].meets_hospital_threshold}

<SiteCallout type="caution" title="Too few hospitals to compare">
Only <Value data={context_header} column=hospital_count /> hospital(s) can be
compared in this exact context, below the 3-hospital floor for market
statistics. The individual published prices are on the
<a href={context_header[0].service_link}>service page</a>.
<a href="/methodology/comparability#the-3-hospital-floor">Why we have a floor.</a>
</SiteCallout>

{:else}

<Grid cols=4>
  <BigValue data={context_header} value=hospital_count title="Comparable hospitals (n)" />
  <BigValue data={context_header} value=median_amount title="Typical hospital price" fmt=usd0 />
  <BigValue data={context_header} value=p10_amount title="Lower hospital price (10th pct)" fmt=usd0 />
  <BigValue data={context_header} value=p90_amount title="Upper hospital price (90th pct)" fmt=usd0 />
</Grid>

Comparison status: **{context_header[0].comparison}** · Comparison confidence:
**{context_header[0].confidence}** ·
{context_header[0].reporting_hospital_count} hospital(s) published this
context{#if context_header[0].contract_count > 0}&nbsp;across
{context_header[0].contract_count} insurer contract(s){/if}. Every statistic
uses one representative price per hospital.

{#if context_header[0].excluded_hospital_count > 0}

<SiteCallout type="caution" title="Some hospitals could not be compared">
{context_header[0].excluded_hospital_count} hospital(s) published this context
but were excluded from the statistics because one insurer contract carried
several different amounts for the exact same context — a hidden pricing
distinction we refuse to average away. See
<a href="/data-quality">data quality</a>.
</SiteCallout>

{/if}

```sql context_hospitals
select
  hospital_display_name,
  '/hospitals/' || hospital_id as hospital_link,
  hospital_amount,
  peer_hospital_count_all,
  market_median_all,
  pct_delta_from_market_median_all,
  case price_position_band
    when 'insufficient_denominator' then 'Too few hospitals to compare'
    when 'very_low' then 'Well below market'
    when 'low' then 'Below market'
    when 'near_market' then 'Near market'
    when 'high' then 'Above market'
    when 'very_high' then 'Well above market'
  end as market_position
from hpt.hospital_service_rankings
where service_context_url_slug = '${params.service_context_url_slug}'
order by hospital_amount desc
```

<BarChart
  data={context_hospitals}
  x=hospital_display_name
  y=hospital_amount
  swapXY=true
  yFmt=usd0
  title="Representative price by hospital (each bar is one hospital's single vote)"
/>

<DataTable data={context_hospitals} link=hospital_link>
  <Column id=hospital_display_name title="Hospital" />
  <Column id=hospital_amount title="This hospital's price" fmt=usd0 />
  <Column id=peer_hospital_count_all title="Peers (n)" />
  <Column id=market_median_all title="Market median" fmt=usd0 />
  <Column id=pct_delta_from_market_median_all title="vs. median" fmt=pct0 />
  <Column id=market_position title="Market position" />
</DataTable>

<SiteCallout type="definition">
"This hospital's price" is the hospital's ONE representative amount for this
exact context — for negotiated rates, the median of its deduplicated insurer
contract amounts, so a rate repeated across many rows counts once. The bars
above are exactly the values behind the percentiles at the top of the page.
See <a href="/methodology/prices">what the price types mean</a>.
</SiteCallout>

{/if}

{/if}
