select pr.*
from {{ ref('slv_base__payer_rates') }} pr
inner join {{ ref('val__payer_rate_rejections') }} r
    on pr.snapshot_id = r.snapshot_id
    and (
        (
            r.source_format_family = 'json'
            and pr.source_standard_charge_id = r.source_standard_charge_id
            and pr.payer_ordinal = r.payer_ordinal
        )
        or (
            r.source_format_family = 'csv'
            and pr.source_row_ordinal = r.row_ordinal
            and pr.source_rate_ordinal = r.source_rate_ordinal
        )
    )
