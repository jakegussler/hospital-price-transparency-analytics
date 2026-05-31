select *
from {{ ref('val__rule_coverage') }}
where primary_model is null
    or implementation_status not like 'implemented%'
