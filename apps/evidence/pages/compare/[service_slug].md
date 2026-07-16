```sql service_header
select
  service_display_label,
  service_display_code,
  service_display_name,
  canonical_code_system,
  match_code,
  description_availability,
  min(relative_weight) as relative_weight,
  min(ms_drg_mdc) as ms_drg_mdc,
  min(ms_drg_type) as ms_drg_type,
  count(*) as context_count,
  max(hospital_count) as max_hospital_count
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
group by all
limit 1
```

{#if service_header.length === 0}

# Service not found

No published data matches this service address. It may have left the corpus in
a data refresh. [Browse all services](/compare).

{:else}

# {service_header[0].service_display_label}

**Billing code:** {service_header[0].service_display_code}

{#if service_header[0].description_availability === 'license_restricted'}

<SiteCallout type="definition" title="Why no description?">
This is a {service_header[0].canonical_code_system.toUpperCase()} code.
CPT/CDT descriptions are licensed and cannot be republished here — that is a
licensing constraint, not a gap in the hospital's file. You can look up code
{service_header[0].match_code} in a licensed reference.
</SiteCallout>

{:else if service_header[0].description_availability === 'not_loaded'}

<SiteCallout type="definition" title="Why no description?">
A public-domain description for this code system has not been loaded into this
project yet. The code still compares correctly across hospitals.
</SiteCallout>

{/if}

This service appears in <Value data={service_header} column=context_count /> published
context(s). A context is the exact combination of price type, payment
methodology, care setting, billing type, and modifiers — prices are only ever
compared within one context, and negotiated methodologies are never mixed (a
per-diem is a daily amount, not an episode price). Pick one:

```sql slug_price_types
select
  amount_kind,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type_label
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
group by amount_kind
order by
  case amount_kind
    when 'discounted_cash' then 1
    when 'negotiated_dollar' then 2
    else 3
  end
```

```sql slug_methodologies
select
  comparison_methodology,
  comparison_methodology_display_label
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
group by 1, 2
order by 1
```

```sql slug_settings
select clean_setting
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
  and comparison_methodology = '${inputs.methodology.value}'
group by clean_setting
order by 1
```

```sql slug_billing
select clean_billing_class
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
  and comparison_methodology = '${inputs.methodology.value}'
  and clean_setting = '${inputs.setting.value}'
group by clean_billing_class
order by 1
```

```sql slug_modifiers
select modifier_display_label
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
  and comparison_methodology = '${inputs.methodology.value}'
  and clean_setting = '${inputs.setting.value}'
  and clean_billing_class = '${inputs.billing_class.value}'
group by modifier_display_label
order by
  case when modifier_display_label like 'No modifier%' then 0 else 1 end,
  modifier_display_label
```

<Dropdown data={slug_price_types} name=price_type value=amount_kind label=price_type_label title="Price type" />

<Dropdown data={slug_methodologies} name=methodology value=comparison_methodology label=comparison_methodology_display_label title="Payment methodology" />

<Dropdown data={slug_settings} name=setting value=clean_setting title="Care setting" />

<Dropdown data={slug_billing} name=billing_class value=clean_billing_class title="Billing type" />

<Dropdown data={slug_modifiers} name=modifier value=modifier_display_label title="Modifiers" />

```sql selected_context
select
  case '${inputs.price_type.value}'
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
  '/compare/context/' || service_context_url_slug as context_link,
  hospital_count,
  reporting_hospital_count::double as reporting_hospital_count,
  excluded_hospital_count::double as excluded_hospital_count,
  contract_count::double as contract_count,
  observation_count,
  payer_count,
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
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
  and comparison_methodology = '${inputs.methodology.value}'
  and clean_setting = '${inputs.setting.value}'
  and clean_billing_class = '${inputs.billing_class.value}'
  and modifier_display_label = '${inputs.modifier.value}'
```

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
where service_url_slug = '${params.service_slug}'
  and amount_kind = '${inputs.price_type.value}'
  and comparison_methodology = '${inputs.methodology.value}'
  and clean_setting = '${inputs.setting.value}'
  and clean_billing_class = '${inputs.billing_class.value}'
  and modifier_display_label = '${inputs.modifier.value}'
order by hospital_amount desc
```

{#if selected_context.length === 0}

<SiteCallout type="scope">
No published prices for this exact combination — pick a different price type or
context above.
</SiteCallout>

{:else}

## Hospital prices for this context

{#if selected_context[0].comparison === 'Too few hospitals'}

<SiteCallout type="caution" title="Too few hospitals to compare">
Only <Value data={selected_context} column=hospital_count /> hospital(s) report
this exact context, below the 3-hospital floor for market statistics. The
individual published prices are shown below, but there is deliberately no
"typical" price, percentile, or ranking — with so few hospitals those numbers
would look precise while meaning almost nothing.
<a href="/methodology/comparability#the-3-hospital-floor">Why we have a floor.</a>
</SiteCallout>

{:else}

<Grid cols=4>
  <BigValue data={selected_context} value=hospital_count title="Comparable hospitals (n)" />
  <BigValue data={selected_context} value=median_amount title="Typical hospital price" fmt=usd0 />
  <BigValue data={selected_context} value=p10_amount title="Lower hospital price (10th pct)" fmt=usd0 />
  <BigValue data={selected_context} value=p90_amount title="Upper hospital price (90th pct)" fmt=usd0 />
</Grid>

Comparison status: **{selected_context[0].comparison}** · Comparison
confidence: **{selected_context[0].confidence}** (based on
{selected_context[0].hospital_count} comparable hospitals) ·
{selected_context[0].reporting_hospital_count} hospital(s) published this
context{#if selected_context[0].contract_count > 0}&nbsp;across
{selected_context[0].contract_count} insurer contract(s){/if}.
Direct link: <a href={selected_context[0].context_link}>this exact context</a>.

{/if}

{#if selected_context[0].methodology_note !== ''}

<SiteCallout type="definition" title={selected_context[0].comparison_methodology_display_label}>
{selected_context[0].methodology_note}
</SiteCallout>

{/if}

{#if selected_context[0].excluded_hospital_count > 0}

<SiteCallout type="caution" title="Some hospitals could not be compared">
{selected_context[0].excluded_hospital_count} hospital(s) published this
context but were excluded from the statistics because one insurer contract
carried several different amounts for the exact same context — a hidden
pricing distinction (often a revenue-code or network difference) we refuse to
average away. Their raw rows remain in the
<a href="/downloads">public downloads</a>; see
<a href="/data-quality">data quality</a> for how exclusions work.
</SiteCallout>

{/if}

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
above are exactly the values behind the percentiles. Price type:
<b>{selected_context[0].price_type_label}</b>
({selected_context[0].comparison_methodology_display_label}).
See <a href="/methodology/prices">what the price types mean</a>.
</SiteCallout>

{/if}

## All published contexts for this service

Every context the corpus hospitals published for this billing code, across all
price types and payment methodologies. Blank statistics mean the context is
below the 3-hospital floor. Comparable rows link to their exact-context page.

```sql all_contexts
select
  case
    when comparison_status <> 'insufficient_denominator'
      then '/compare/context/' || service_context_url_slug
  end as context_link,
  case amount_kind
    when 'gross_charge' then 'List price'
    when 'discounted_cash' then 'Cash price'
    when 'negotiated_dollar' then 'Negotiated rate'
  end as price_type,
  comparison_methodology_display_label as methodology,
  case clean_setting
    when 'unspecified' then 'Not specified'
    else clean_setting
  end as setting,
  case clean_billing_class
    when 'unspecified' then 'Not labeled by hospital'
    else clean_billing_class
  end as billing_type,
  modifier_display_label,
  hospital_count,
  observation_count,
  case comparison_status
    when 'insufficient_denominator' then 'Too few hospitals'
    when 'described_comparable' then 'Comparable (described)'
    when 'code_only_comparable' then 'Comparable (code only)'
  end as comparison,
  median_amount,
  p10_amount,
  p90_amount
from hpt.service_market_explorer
where service_url_slug = '${params.service_slug}'
order by amount_kind, comparison_methodology, clean_setting,
  clean_billing_class, modifier_display_label
```

<DataTable data={all_contexts} link=context_link rows=25>
  <Column id=price_type title="Price type" />
  <Column id=methodology title="Methodology" />
  <Column id=setting title="Care setting" />
  <Column id=billing_type title="Billing type" />
  <Column id=modifier_display_label title="Modifiers" />
  <Column id=hospital_count title="Comparable hospitals (n)" />
  <Column id=observation_count title="Price rows" fmt=num0 />
  <Column id=comparison title="Comparison status" />
  <Column id=median_amount title="Typical hospital price" fmt=usd0 />
  <Column id=p10_amount title="Lower hospital price (10th pct)" fmt=usd0 />
  <Column id=p90_amount title="Upper hospital price (90th pct)" fmt=usd0 />
</DataTable>

{/if}
