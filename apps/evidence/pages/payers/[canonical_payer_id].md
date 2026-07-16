```sql payer
select
  *,
  case
    when payer_parent_name is not null and payer_parent_name <> ''
      then 'Part of ' || payer_parent_name || '. '
    else ''
  end as parent_prefix,
  (contexts_meeting_payer_floor = 0) as no_payer_floor_met
from hpt.payer_overview
where canonical_payer_id = '${params.canonical_payer_id}'
```

{#if payer.length === 0}

# Insurer not found

No matched insurer in the current corpus has this address.
[Back to insurers.](/payers)

{:else}

# {payer[0].payer_display_name}

{payer[0].parent_prefix}Matched insurer identity. Only rates whose published
insurer name matched this identity appear here.

<Grid cols=4>
  <BigValue data={payer} value=hospital_count title="Hospitals" />
  <BigValue data={payer} value=service_count title="Services" fmt=num0 />
  <BigValue data={payer} value=contract_context_count title="Rate contexts" fmt=num0 />
  <BigValue data={payer} value=contexts_meeting_payer_floor title="Contexts meeting 3-hospital floor" fmt=num0 />
</Grid>

## Negotiated rates vs. hospitals' cash prices

For each rate context where the hospital also published a cash price AND the
comparison is meaningful, we compare this insurer's negotiated rate to that
cash price. This comparison is within one hospital's file, so it needs no
cross-hospital floor — but it is methodology-guarded: a per-diem rate is a
DAILY amount and is never labeled above or below a cash price.

```sql cash_summary
select
  case bands.band
    when 'below_cash' then 'Negotiated below cash price'
    when 'equal_to_cash' then 'Same as cash price'
    when 'above_cash' then 'Negotiated ABOVE cash price'
    when 'per_diem_incompatible' then 'Per-diem (daily) rate — not comparable'
    when 'ambiguous' then 'Contract has mixed amounts — excluded'
  end as comparison,
  case bands.band
    when 'below_cash' then below_cash_context_count
    when 'equal_to_cash' then equal_to_cash_context_count
    when 'above_cash' then above_cash_context_count
    when 'per_diem_incompatible' then cash_incompatible_context_count
    when 'ambiguous' then ambiguous_context_count
  end as context_count
from hpt.payer_overview
cross join (
  select unnest([
    'below_cash', 'equal_to_cash', 'above_cash',
    'per_diem_incompatible', 'ambiguous'
  ]) as band
) as bands
where canonical_payer_id = '${params.canonical_payer_id}'
order by
  case bands.band
    when 'below_cash' then 1
    when 'equal_to_cash' then 2
    when 'above_cash' then 3
    when 'per_diem_incompatible' then 4
    else 5
  end
```

<BarChart
  data={cash_summary}
  x=comparison
  y=context_count
  swapXY=true
  sort=false
  yFmt=num0
  title="Rate contexts vs. the hospital's own cash price"
/>

<SiteCallout type="caution">
A negotiated rate above the cash price is a signal to investigate, not proof of
overpayment — the two published numbers can cover different bundles, units, or
plan contexts. Per-diem (daily) rates and contracts with mixed amounts are
never counted as above or below cash.
<a href="/methodology/prices#negotiated-vs-cash">How to read this comparison.</a>
</SiteCallout>

## This insurer across hospitals

Where this insurer has comparable rates at 3+ hospitals for the exact same
service context, each rate is placed against the insurer's own market median.

```sql position_summary
select
  case bands.band
    when 'well_below' then 'Well below insurer median (25%+)'
    when 'below' then 'Below insurer median (10-25%)'
    when 'near' then 'Near insurer median'
    when 'above' then 'Above insurer median (10-25%)'
    when 'well_above' then 'Well above insurer median (25%+)'
  end as position,
  case bands.band
    when 'well_below' then contexts_well_below_payer_market
    when 'below' then contexts_below_payer_market
    when 'near' then contexts_near_payer_market
    when 'above' then contexts_above_payer_market
    when 'well_above' then contexts_well_above_payer_market
  end as context_count
from hpt.payer_overview
cross join (
  select unnest(['well_below', 'below', 'near', 'above', 'well_above']) as band
) as bands
where canonical_payer_id = '${params.canonical_payer_id}'
order by
  case bands.band
    when 'well_below' then 1
    when 'below' then 2
    when 'near' then 3
    when 'above' then 4
    else 5
  end
```

{#if payer[0].no_payer_floor_met}

<SiteCallout type="scope" title="No cross-hospital positions yet">
This insurer has no service context with comparable rates at 3 or more
hospitals in the current corpus, so no rate is placed against an
insurer-market median. Rates are still browsable below.
</SiteCallout>

{:else}

<DataTable data={position_summary}>
  <Column id=position title="Position vs. this insurer's median" />
  <Column id=context_count title="Contexts" fmt=num0 />
</DataTable>

{/if}

## Browse this insurer's rates

```sql payer_hospitals
select distinct hospital_display_name
from hpt.payer_contracting_explorer
where canonical_payer_id = '${params.canonical_payer_id}'
order by 1
```

<Dropdown data={payer_hospitals} name=hospital value=hospital_display_name title="Hospital">
  <DropdownOption valueLabel="All hospitals" value="%" />
</Dropdown>

<TextInput
  name=rate_search
  title="Search services"
  placeholder="Service name or billing code"
/>

```sql rates_count
select count(*) as n
from hpt.payer_contracting_explorer
where canonical_payer_id = '${params.canonical_payer_id}'
  and hospital_display_name like '${inputs.hospital.value}'
  and (
    service_display_label ilike '%${inputs.rate_search}%'
    or match_code ilike '%${inputs.rate_search}%'
  )
```

```sql rates
select
  hospital_display_name,
  service_display_label,
  case
    when coalesce(context_hospital_count, 0) >= 3
      then '/compare/context/' || service_context_url_slug
    else '/compare/' || service_url_slug
  end as service_link,
  case clean_setting
    when 'unspecified' then 'Not specified'
    else clean_setting
  end as setting,
  comparison_methodology_display_label as methodology,
  negotiated_dollar,
  hospital_cash_amount,
  case cash_comparison_band
    when 'below_cash' then 'Below cash'
    when 'equal_to_cash' then 'Same as cash'
    when 'above_cash' then 'Above cash'
    when 'cash_unavailable' then 'No cash price'
    when 'per_diem_incompatible' then 'Daily rate — not comparable'
    when 'ambiguous_negotiated_context' then 'Mixed amounts — excluded'
  end as vs_cash,
  case contract_position_band
    when 'insufficient_denominator' then 'Too few hospitals'
    when 'ambiguous_negotiated_context' then 'Mixed amounts — excluded'
    when 'well_below_payer_market' then 'Well below insurer median'
    when 'below_payer_market' then 'Below insurer median'
    when 'near_payer_market' then 'Near insurer median'
    when 'above_payer_market' then 'Above insurer median'
    when 'well_above_payer_market' then 'Well above insurer median'
  end as vs_insurer_market,
  payer_hospital_count
from hpt.payer_contracting_explorer
where canonical_payer_id = '${params.canonical_payer_id}'
  and hospital_display_name like '${inputs.hospital.value}'
  and (
    service_display_label ilike '%${inputs.rate_search}%'
    or match_code ilike '%${inputs.rate_search}%'
  )
order by hospital_display_name, service_display_label
limit 500
```

 {(rates_count[0]?.n ?? 0).toLocaleString()} rate contexts match; the table shows the first 500.

<DataTable data={rates} link=service_link rows=25>
  <Column id=hospital_display_name title="Hospital" />
  <Column id=service_display_label title="Service" />
  <Column id=setting title="Care setting" />
  <Column id=methodology title="Methodology" />
  <Column id=negotiated_dollar title="Negotiated rate" fmt=usd0 />
  <Column id=hospital_cash_amount title="Hospital cash price" fmt=usd0 />
  <Column id=vs_cash title="vs. cash" />
  <Column id=vs_insurer_market title="vs. insurer market" />
  <Column id=payer_hospital_count title="Insurer hospitals (n)" />
</DataTable>

{/if}
