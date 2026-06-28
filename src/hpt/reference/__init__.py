"""External reference-data loaders (green-light, public-domain code systems).

Reference data (CMS/FDA code descriptions, groupers, payment-system context) is
independently snapshotted source data, not part of the hospital-MRF snapshot
lineage. It is downloaded from an authoritative source, parsed, and written to
Parquet under ``{HPT_REFERENCE_ROOT}/{table}/release_date={date}/`` with full
provenance (``source_url``, ``code_edition``, ``retrieved_at``). dbt exposes it
through the ``reference`` source and normalizes it into the Silver code
dimension that the Gold ``gld_dim__service_code`` seam joins for descriptions.

See ``docs/local/external-data-enrichment.md`` and decision 0019.
"""

from __future__ import annotations

from hpt.reference.code_descriptions import (
    REFERENCE_SOURCES,
    load_reference,
    parse_ms_drg_table5,
)
from hpt.reference.config import ReferenceStorageConfig
from hpt.reference.registry import ReferenceSource, load_reference_sources

__all__ = [
    "REFERENCE_SOURCES",
    "ReferenceStorageConfig",
    "ReferenceSource",
    "load_reference",
    "load_reference_sources",
    "parse_ms_drg_table5",
]
