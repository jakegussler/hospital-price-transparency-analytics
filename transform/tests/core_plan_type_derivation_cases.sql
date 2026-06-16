{{ config(tags=['silver_core']) }}
-- Unit coverage for hpt_derive_plan_type: whole-word single-token extraction
-- with ambiguity -> null. The tricky strings are drawn from real
-- clean_plan_name values that naive substring matching would mistag:
--   * coded suffixes "hmox/ppox/posx" are not plan-type tokens
--   * "dhmo" (dental HMO) is not a word-boundary "hmo"
--   * "mcrppo" (compact Medicare PPO code) is not a word-boundary "ppo"
--   * "ppo hmo" is ambiguous (two distinct tokens) and must resolve to null
-- Returns offending rows when the macro output disagrees with the expectation.
with cases as (
    select *
    from (
        values
            ('ppo', 'ppo'),
            ('uhc options ppo', 'ppo'),
            ('united healthcare ppo adult', 'ppo'),
            ('ucd hb uhc non hmo', 'hmo'),
            ('medicare advantage-ppo', 'ppo'),
            ('humana choicecare ppo', 'ppo'),
            ('cigna dental ppo', 'ppo'),
            ('select epo plan', 'epo'),
            ('point of service pos plan', 'pos'),
            ('hdhp gold', 'hdhp'),
            ('pffs network', 'pffs'),
            ('ucd hb cigna ppo hmo', cast(null as varchar)),
            ('commercial hmox - ppox & posx', cast(null as varchar)),
            ('cigna dhmo', cast(null as varchar)),
            ('mcrppo', cast(null as varchar)),
            ('aetna whole health pediatric', cast(null as varchar)),
            ('medicare advantage esa', cast(null as varchar)),
            (cast(null as varchar), cast(null as varchar)),
            ('', cast(null as varchar))
    ) as t (clean_plan_name, expected_plan_type)
)

select
    clean_plan_name,
    expected_plan_type,
    {{ hpt_derive_plan_type('clean_plan_name') }} as actual_plan_type
from cases
where {{ hpt_derive_plan_type('clean_plan_name') }} is distinct from expected_plan_type
