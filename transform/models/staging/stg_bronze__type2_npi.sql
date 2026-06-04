select
    snapshot_id,
    cast(npi_ordinal as integer) as npi_ordinal,
    npi as raw_npi,
    {{ hpt_clean_display_text('npi') }} as clean_npi
from {{ hpt_staging_source(source('bronze', 'type2_npi')) }}
where 1 = 1
    {{ hpt_snapshot_filter() }}
