---
title: Compare Prices
hide_title: true
sidebar_position: 1
---

# Compare Prices

Search everything hospitals published, one price type at a time. The same
billing code can appear several times because prices legitimately differ by
care setting, billing type, and modifiers — we never merge those contexts, and
we never rank different price types against each other.

<SiteCallout type="definition">
Every row shows its hospital count ("n"). Market statistics (typical price,
percentiles, spread) exist only where at least 3 hospitals report the exact
same context; other rows are labeled "Too few hospitals". See
<a href="/methodology/comparability">how comparison works</a>.
</SiteCallout>

```sql settings
select distinct clean_setting from hpt.service_market_explorer order by 1
```

```sql billing_classes
select distinct clean_billing_class from hpt.service_market_explorer order by 1
```

<TextInput
  name=service_search
  title="Search services"
  placeholder="Service name or billing code, e.g. joint replacement or 470"
/>

<ButtonGroup name=price_type title="Price type">
  <ButtonGroupItem valueLabel="Cash price" value="discounted_cash" default />
  <ButtonGroupItem valueLabel="Negotiated rate" value="negotiated_dollar" />
  <ButtonGroupItem valueLabel="List price" value="gross_charge" />
</ButtonGroup>

<ButtonGroup name=scope title="Which contexts">
  <ButtonGroupItem valueLabel="Comparable only" value="comparable" default />
  <ButtonGroupItem valueLabel="Everything published" value="all" />
</ButtonGroup>

<Dropdown data={settings} name=setting value=clean_setting title="Care setting">
  <DropdownOption valueLabel="All settings" value="%" />
</Dropdown>

<Dropdown data={billing_classes} name=billing_class value=clean_billing_class title="Billing type">
  <DropdownOption valueLabel="All billing types" value="%" />
</Dropdown>

```sql services_count
select count(*) as matching_rows
from hpt.service_market_explorer
where amount_kind = '${inputs.price_type}'
  and (
    service_display_label ilike '%${inputs.service_search}%'
    or match_code ilike '%${inputs.service_search}%'
  )
  and clean_setting like '${inputs.setting.value}'
  and clean_billing_class like '${inputs.billing_class.value}'
  and ('${inputs.scope}' = 'all' or comparison_status <> 'insufficient_denominator')
```

```sql services
select
  service_display_label,
  '/compare/' || service_url_slug as service_link,
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
  payer_count,
  case comparison_status
    when 'insufficient_denominator' then 'Too few hospitals'
    when 'described_comparable' then 'Comparable (described)'
    when 'code_only_comparable' then 'Comparable (code only)'
  end as comparison,
  median_amount,
  p10_amount,
  p90_amount,
  spread_ratio_p90_to_p10
from hpt.service_market_explorer
where amount_kind = '${inputs.price_type}'
  and (
    service_display_label ilike '%${inputs.service_search}%'
    or match_code ilike '%${inputs.service_search}%'
  )
  and clean_setting like '${inputs.setting.value}'
  and clean_billing_class like '${inputs.billing_class.value}'
  and ('${inputs.scope}' = 'all' or comparison_status <> 'insufficient_denominator')
order by
  case when comparison_status = 'insufficient_denominator' then 1 else 0 end,
  hospital_count desc,
  service_display_label
limit 500
```

{#if services.length === 0}

<SiteCallout type="scope" title="No matching contexts">
Nothing matches these filters. If "Which contexts" is set to <b>Comparable
only</b>, note that the current corpus has no context reported by 3 or more
hospitals yet — switch to <b>Everything published</b> to browse all published
prices (individually visible, but not comparable across hospitals).
</SiteCallout>

{:else}

 {(services_count[0]?.matching_rows ?? 0).toLocaleString()} contexts match; the table shows the first 500. Click a row for every hospital's price on that
service.

<DataTable data={services} link=service_link rows=25>
  <Column id=service_display_label title="Service" />
  <Column id=setting title="Care setting" />
  <Column id=billing_type title="Billing type" />
  <Column id=modifier_display_label title="Modifiers" />
  <Column id=hospital_count title="Hospitals (n)" />
  <Column id=comparison title="Comparison status" />
  <Column id=median_amount title="Typical (median)" fmt=usd0 />
  <Column id=p10_amount title="Lower (10th pct)" fmt=usd0 />
  <Column id=p90_amount title="Upper (90th pct)" fmt=usd0 />
  <Column id=spread_ratio_p90_to_p10 title="Spread (x)" fmt=num1 />
</DataTable>

{/if}

<SiteCallout type="caution">
A service showing "Description not available" usually carries a CPT code:
CPT descriptions are licensed by the AMA and cannot be republished here. The
code itself still compares correctly. Blank price columns mean the context is
below the 3-hospital floor — the individual hospital prices are still on the
service page.
</SiteCallout>
