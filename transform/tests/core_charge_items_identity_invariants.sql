-- Targeted invariants on the derived item-identity fields: the basis column
-- must agree with which signatures exist, confidence must agree with basis,
-- a specific signature implies a full signature, and every item gets an ID.
select
    silver_charge_item_id,
    service_item_id,
    service_item_identity_basis,
    service_item_identity_confidence,
    code_signature_specific,
    code_signature_all
from {{ hpt_scoped_ref('slv_core__charge_items') }}
where
    service_item_id is null
    or (
        service_item_identity_basis = 'specific_code'
        and (code_signature_specific is null
             or service_item_identity_confidence <> 'high')
    )
    or (
        service_item_identity_basis = 'categorical_code'
        and (code_signature_specific is not null
             or code_signature_all is null
             or service_item_identity_confidence <> 'medium')
    )
    or (
        service_item_identity_basis = 'uncoded'
        and (code_signature_all is not null
             or service_item_identity_confidence <> 'low')
    )
    or (code_signature_specific is not null and code_signature_all is null)
