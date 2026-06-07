select {{ hpt_validation_common_columns() }} from {{ ref('val__header_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__metadata_child_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__structural_parse_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__charge_item_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__code_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__drug_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__standard_charge_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__payer_rate_violations') }}
union all
select {{ hpt_validation_common_columns() }} from {{ ref('val__modifier_violations') }}
