"""Streaming parser for CMS JSON Machine-Readable Files.



1. Pass 1 — :func:`ijson.parse` walks the top-level header scalars and simple
   arrays, stopping at the ``standard_charge_information`` ``start_array``
   event. Produces the ``hospital_mrf_snapshots``, ``hospital_locations``,
   and ``type2_npi`` rows.
2. Pass 2 — :func:`ijson.items` on ``modifier_information.item`` streams the
   optional top-level modifier dimension. Small array; emitted as a single
   batch.
3. Pass 3 — :func:`ijson.items` on ``standard_charge_information.item``
   streams the large charge array. Each item is validated by the Pydantic
   model :class:`~hpt.ingest.cms_json_models.StandardChargeInformation`
   and fanned out into rows across six child tables. Invalid items are
   written to the quarantine directory and skipped.
"""

from __future__ import annotations

import gzip
import json
import logging
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import ijson
import polars as pl
from pydantic import ValidationError

from hpt.ingest.cms_json_models import (
    ModifierInformation,
    StandardChargeInformation,
)
from hpt.parsers.base import BaseParser
from hpt.parsers.schemas import BRONZE_SCHEMAS

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

_CHARGE_TABLES: tuple[str, ...] = (
    "standard_charge_info",
    "code_information",
    "drug_information",
    "standard_charges",
    "standard_charge_modifiers",
    "payers_information",
)


def _to_float(value: Decimal | float | int | None) -> float | None:
    """Convert numeric Pydantic fields to ``float`` for Bronze Float64 columns."""
    if value is None:
        return None
    if isinstance(value, float):
        return value
    return float(value)


class JsonMrfParser(BaseParser):
    """Parse CMS JSON MRF files using streaming (ijson)."""

    def parse(self, file_path: Path) -> Iterator[dict[str, pl.DataFrame]]:
        yield self._header_batch(file_path)
        yield from self._parse_modifiers(file_path)
        yield from self._parse_charges(file_path)

    # ------------------------------------------------------------------
    # Pass 1 — header
    # ------------------------------------------------------------------

    def _header_batch(self, file_path: Path) -> dict[str, pl.DataFrame]:
        snapshot_record, location_rows, npi_rows = self._parse_header(file_path)
        return {
            "hospital_mrf_snapshots": _df(
                [snapshot_record], BRONZE_SCHEMAS["hospital_mrf_snapshots"]
            ),
            "hospital_locations": _df(
                location_rows, BRONZE_SCHEMAS["hospital_locations"]
            ),
            "type2_npi": _df(npi_rows, BRONZE_SCHEMAS["type2_npi"]),
        }

    def _parse_header(
        self, file_path: Path
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Stream the JSON header, stopping before the charge array."""
        h: dict[str, Any] = {}

        with _open_maybe_gz(file_path) as f:
            for prefix, event, value in ijson.parse(f, use_float=True):
                if prefix == "hospital_name":
                    h["hospital_name"] = value
                elif prefix == "last_updated_on":
                    h["last_updated_on"] = value
                elif prefix == "version":
                    h["version"] = value
                elif prefix == "attestation.attestation":
                    h["attestation_text"] = value
                elif prefix == "attestation.confirm_attestation":
                    h["confirm_attestation"] = str(value).lower()
                elif prefix == "attestation.attester_name":
                    h["attester_name"] = value
                elif prefix == "license_information.state":
                    h["state"] = value
                elif prefix == "license_information.license_number":
                    h["license_number"] = value
                elif prefix == "location_name.item":
                    h.setdefault("location_names", []).append(value)
                elif prefix == "hospital_address.item":
                    h.setdefault("hospital_addresses", []).append(value)
                elif prefix == "type_2_npi.item":
                    h.setdefault("type_2_npis", []).append(value)
                elif (
                    prefix == "standard_charge_information"
                    and event == "start_array"
                ):
                    break

        snapshot_id = self.snapshot_meta["snapshot_id"]
        snapshot_record = self._build_snapshot_record(h)

        location_names = h.get("location_names") or []
        hospital_addrs = h.get("hospital_addresses") or []
        n_locations = max(len(location_names), len(hospital_addrs))
        location_rows = [
            {
                "snapshot_id": snapshot_id,
                "location_ordinal": i,
                "location_name": (
                    location_names[i] if i < len(location_names) else None
                ),
                "hospital_address": (
                    hospital_addrs[i] if i < len(hospital_addrs) else None
                ),
            }
            for i in range(n_locations)
        ]

        npi_rows = [
            {"snapshot_id": snapshot_id, "npi": npi, "npi_ordinal": i}
            for i, npi in enumerate(h.get("type_2_npis", []))
        ]

        return snapshot_record, location_rows, npi_rows

    def _build_snapshot_record(self, h: dict[str, Any]) -> dict[str, Any]:
        """Merge pipeline-generated metadata with source-derived header fields."""
        meta = self.snapshot_meta
        return {
            "snapshot_id": meta["snapshot_id"],
            "hospital_id": meta.get("hospital_id"),
            "reported_hospital_name": h.get("hospital_name"),
            "source_url": meta.get("source_url"),
            "source_file_name": meta.get("source_file_name"),
            "source_format": meta.get("source_format", "json"),
            "file_hash": meta.get("file_hash"),
            "ingested_at": _iso(meta.get("ingested_at")),
            "published_last_updated_on": h.get("last_updated_on"),
            "schema_version": meta.get("schema_version") or h.get("version"),
            "is_current_snapshot": bool(meta.get("is_current_snapshot", True)),
            "valid_from": _iso(meta.get("valid_from")),
            "valid_to": _iso(meta.get("valid_to")),
            "attestation": h.get("attestation_text"),
            "confirm_attestation": h.get("confirm_attestation"),
            "attester_name": h.get("attester_name"),
            "reported_state": h.get("state"),
            "license_number": h.get("license_number"),
        }

    # ------------------------------------------------------------------
    # Pass 2 — modifier_information
    # ------------------------------------------------------------------

    def _parse_modifiers(
        self, file_path: Path
    ) -> Iterator[dict[str, pl.DataFrame]]:
        snapshot_id = self.snapshot_meta["snapshot_id"]
        modifiers_rows: list[dict[str, Any]] = []
        modifier_payer_rows: list[dict[str, Any]] = []

        with _open_maybe_gz(file_path) as f:
            for ordinal, raw_item in enumerate(
                ijson.items(f, "modifier_information.item", use_float=True)
            ):
                try:
                    mi = ModifierInformation.model_validate(raw_item)
                except ValidationError as exc:
                    self._quarantine(
                        "modifier_information", ordinal, raw_item, exc
                    )
                    continue

                modifier_code_id = f"{snapshot_id}_{ordinal}"
                modifiers_rows.append(
                    {
                        "modifier_code_id": modifier_code_id,
                        "snapshot_id": snapshot_id,
                        "code": mi.code,
                        "description": mi.description,
                        "setting": mi.setting.value if mi.setting else None,
                    }
                )
                for payer in mi.modifier_payer_information:
                    modifier_payer_rows.append(
                        {
                            "snapshot_id": snapshot_id,
                            "modifier_code_id": modifier_code_id,
                            "payer_name": payer.payer_name,
                            "plan_name": payer.plan_name,
                            "description": payer.description,
                        }
                    )

        yield {
            "modifiers": _df(modifiers_rows, BRONZE_SCHEMAS["modifiers"]),
            "modifier_payer_info": _df(
                modifier_payer_rows, BRONZE_SCHEMAS["modifier_payer_info"]
            ),
        }

    # ------------------------------------------------------------------
    # Pass 3 — standard_charge_information
    # ------------------------------------------------------------------

    def _parse_charges(
        self, file_path: Path
    ) -> Iterator[dict[str, pl.DataFrame]]:
        accumulator: dict[str, list[dict[str, Any]]] = defaultdict(list)
        processed = 0

        with _open_maybe_gz(file_path) as f:
            for item_ordinal, raw_item in enumerate(
                ijson.items(
                    f, "standard_charge_information.item", use_float=True
                )
            ):
                try:
                    sci = StandardChargeInformation.model_validate(raw_item)
                except ValidationError as exc:
                    self._quarantine(
                        "standard_charge_information",
                        item_ordinal,
                        raw_item,
                        exc,
                    )
                    continue

                flat = self._flatten_sci(sci, item_ordinal)
                for table_name, rows in flat.items():
                    accumulator[table_name].extend(rows)

                processed += 1
                if processed % BATCH_SIZE == 0:
                    yield _accumulator_to_batch(accumulator)
                    accumulator = defaultdict(list)

        if any(accumulator.values()):
            yield _accumulator_to_batch(accumulator)

    def _flatten_sci(
        self,
        sci: StandardChargeInformation,
        item_ordinal: int,
    ) -> dict[str, list[dict[str, Any]]]:
        """Explode a single standard_charge_information item into Bronze rows."""
        snapshot_id = self.snapshot_meta["snapshot_id"]
        charge_item_id = f"{snapshot_id}_{item_ordinal}"

        out: dict[str, list[dict[str, Any]]] = {
            table: [] for table in _CHARGE_TABLES
        }

        out["standard_charge_info"].append(
            {
                "charge_item_id": charge_item_id,
                "snapshot_id": snapshot_id,
                "description": sci.description,
                "item_ordinal": item_ordinal,
            }
        )

        for code_ord, code in enumerate(sci.code_information):
            out["code_information"].append(
                {
                    "snapshot_id": snapshot_id,
                    "charge_item_id": charge_item_id,
                    "code_ordinal": code_ord,
                    "code": code.code,
                    "type": code.type.value,
                }
            )

        if sci.drug_information is not None:
            out["drug_information"].append(
                {
                    "snapshot_id": snapshot_id,
                    "charge_item_id": charge_item_id,
                    "unit": _to_float(sci.drug_information.unit),
                    "type": sci.drug_information.type.value,
                }
            )

        for charge_ord, charge in enumerate(sci.standard_charges):
            standard_charge_id = f"{charge_item_id}_{charge_ord}"
            out["standard_charges"].append(
                {
                    "standard_charge_id": standard_charge_id,
                    "snapshot_id": snapshot_id,
                    "charge_item_id": charge_item_id,
                    "charge_ordinal": charge_ord,
                    "minimum": _to_float(charge.minimum),
                    "maximum": _to_float(charge.maximum),
                    "gross_charge": _to_float(charge.gross_charge),
                    "discounted_cash": _to_float(charge.discounted_cash),
                    "setting": charge.setting.value,
                    "billing_class": charge.billing_class,
                    "additional_generic_notes": charge.additional_generic_notes,
                }
            )

            for mod_ord, mod_code in enumerate(charge.modifier_code or []):
                out["standard_charge_modifiers"].append(
                    {
                        "snapshot_id": snapshot_id,
                        "standard_charge_id": standard_charge_id,
                        "modifier_code": mod_code,
                        "modifier_ordinal": mod_ord,
                    }
                )

            for payer_ord, payer in enumerate(charge.payers_information or []):
                out["payers_information"].append(
                    {
                        "snapshot_id": snapshot_id,
                        "standard_charge_id": standard_charge_id,
                        "payer_ordinal": payer_ord,
                        "payer_name": payer.payer_name,
                        "plan_name": payer.plan_name,
                        "methodology": payer.methodology.value,
                        "standard_charge_dollar": _to_float(
                            payer.standard_charge_dollar
                        ),
                        "standard_charge_percentage": _to_float(
                            payer.standard_charge_percentage
                        ),
                        "standard_charge_algorithm": payer.standard_charge_algorithm,
                        "median_amount": _to_float(payer.median_amount),
                        "tenth_percentile": _to_float(payer.tenth_percentile),
                        "ninetieth_percentile": _to_float(
                            payer.ninetieth_percentile
                        ),
                        "count": payer.count,
                        "additional_payer_notes": payer.additional_payer_notes,
                    }
                )

        return out

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    def _quarantine(
        self,
        section: str,
        ordinal: int,
        raw: Any,
        exc: Exception,
    ) -> None:
        """Write a failed item to ``quarantine/snapshot_id=<id>/<section>.jsonl``."""
        snapshot_id = self.snapshot_meta["snapshot_id"]
        q_dir = self.quarantine_root / f"snapshot_id={snapshot_id}"
        q_dir.mkdir(parents=True, exist_ok=True)
        q_path = q_dir / f"{section}.jsonl"

        record = {
            "section": section,
            "ordinal": ordinal,
            "error": str(exc),
            "raw": raw,
        }
        with q_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

        logger.warning(
            "validation_error",
            extra={
                "snapshot_id": snapshot_id,
                "section": section,
                "ordinal": ordinal,
                "error": str(exc),
            },
        )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _accumulator_to_batch(
    accumulator: dict[str, list[dict[str, Any]]],
) -> dict[str, pl.DataFrame]:
    """Convert a per-table row accumulator into typed Polars DataFrames."""
    return {
        table_name: _df(rows, BRONZE_SCHEMAS[table_name])
        for table_name, rows in accumulator.items()
    }


def _df(
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType],
) -> pl.DataFrame:
    """Build a Polars DataFrame with a fixed schema, handling empty row sets."""
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema)


def _iso(value: Any) -> str | None:
    """Render datetime-ish values as ISO-8601 strings; pass through strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@contextmanager
def _open_maybe_gz(file_path: Path):
    """Yield a binary stream for *file_path*, transparently decompressing gzip.

    Detects gzip by the ``.gz`` suffix. Falls back to the sniffer's magic-byte
    detection if the suffix is ambiguous would be overkill here — downstream
    parsers operate on post-download paths that either retain ``.gz`` or
    have been decompressed in-place by :mod:`hpt.ingest.compression`.
    """
    path_str = str(file_path).lower()
    if path_str.endswith(".gz"):
        with gzip.open(file_path, "rb") as f:
            yield f
    else:
        with open(file_path, "rb") as f:
            yield f
