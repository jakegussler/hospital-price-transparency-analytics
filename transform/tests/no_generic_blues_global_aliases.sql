select *
from {{ ref('payer_aliases') }}
where active = true
    and match_scope = 'global'
    and clean_payer_name in (
        'bcbs',
        'blue cross',
        'bluecard - network p',
        'bluecard - network s'
    )
