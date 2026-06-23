{{ config(severity='warn', tags=['silver_audit']) }}

-- Warn-only duplicate-context contract for payer rates. The positional
-- silver_payer_rate_id stays unique, so this is the only place a genuine
-- business-grain repeat (same item + setting + billing class + canonical payer
-- + plan + methodology + modifier signature + amount_kind within a snapshot)
-- surfaces. Warn rather than error because CMS source files legitimately repeat
-- a context; the productionize plan routes these to observability
-- (slv_audit__payer_rate_duplicate_context) instead of dropping rows. Each row
-- returned is one duplicated comparable rate unit.
select *
from {{ ref('slv_audit__payer_rate_duplicate_context') }}
