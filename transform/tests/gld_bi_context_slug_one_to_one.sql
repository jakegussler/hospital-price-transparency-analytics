-- Contract guard (decision 0021): service_context_url_slug must identify
-- exactly one exact comparison context, and each context must carry exactly one
-- slug. The slug embeds a 10-char prefix of service_context_key plus normalized
-- labels; if two contexts ever collided (or one context produced two slugs),
-- public exact-context URLs would silently merge or split methodology-specific
-- comparisons. Checked across every BI mart that publishes the slug.
with slugs as (
    select service_context_url_slug, service_context_key
    from {{ ref('gld_bi__service_market_explorer') }}
    union all
    select service_context_url_slug, service_context_key
    from {{ ref('gld_bi__hospital_service_rankings') }}
    union all
    select service_context_url_slug, service_context_key
    from {{ ref('gld_bi__payer_contracting_explorer') }}
    union all
    select service_context_url_slug, service_context_key
    from {{ ref('gld_bi__featured_services') }}
)

select service_context_url_slug
from slugs
group by service_context_url_slug
having count(distinct service_context_key) > 1

union all

select service_context_key as service_context_url_slug
from slugs
group by service_context_key
having count(distinct service_context_url_slug) > 1
