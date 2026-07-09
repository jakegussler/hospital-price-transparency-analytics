-- Contract guard: service_url_slug must identify exactly one service code
-- cohort. The slug is derived by normalizing (canonical_code_system,
-- match_code) to a URL-safe string (hpt_service_url_slug); if two distinct
-- match_codes ever normalize to the same slug (e.g. codes differing only by
-- punctuation), public service URLs would silently merge two different
-- services. Fail on any slug mapping to more than one service_code_key.
select service_url_slug
from {{ ref('gld_bi__service_market_explorer') }}
group by service_url_slug
having count(distinct service_code_key) > 1
