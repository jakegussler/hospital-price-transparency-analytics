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
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import ijson
import polars as pl
from pydantic import ValidationError

from hpt.ingest.cms_json_models import (
    JSON_SCHEMA_ATTEMPT_ORDERS,
    ModifierInformation,
    StandardChargeInformation,
    normalize_json_schema_family,
    parser_schema_version_for_family,
)
from hpt.parsers.base import BaseParser
from hpt.parsers.helpers import _df, _iso
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
    "json_record_parse_diagnostics",
)


def _to_text(value: Decimal | float | int | None) -> str | None:
    """Render numeric Pydantic fields as text for Bronze ``Utf8`` columns.

    Bronze preserves the source numeric representation; dbt staging is the type
    boundary that casts these strings to ``decimal``/``double`` (see ADR 0010).
    ``Decimal`` keeps its plain string form rather than being routed through
    ``float``, so no precision is lost before dbt.
    """
    if value is None:
        return None
    return str(value)


@dataclass(frozen=True)
class ParsedChargeItem:
    model: StandardChargeInformation | None
    reported_schema_version: str | None
    reported_schema_family: str | None
    parser_schema_family: str | None
    parser_schema_version: str | None
    attempted_schema_families: list[str]
    errors_by_family: dict[str, dict[str, Any]]

    @property
    def schema_version_mismatch(self) -> bool:
        if self.reported_schema_family is None or self.parser_schema_family is None:
            return False
        return self.reported_schema_family != self.parser_schema_family

    @property
    def used_fallback(self) -> bool:
        return self.model is not None and len(self.errors_by_family) > 0


class JsonMrfParser(BaseParser):
    """Parse CMS JSON MRF files using streaming (ijson)."""

    def parse(self, file_path: Path) -> Iterator[dict[str, pl.DataFrame]]:
        snapshot_id = self.snapshot_meta["snapshot_id"]
        self._quarantine_counts: dict[str, int] = defaultdict(int)

        logger.info(
            "json_parse_pass_start",
            extra={"snapshot_id": snapshot_id, "pass_name": "header"},
        )
        header_batch = self._header_batch(file_path)
        logger.info(
            "json_parse_pass_complete",
            extra={
                "snapshot_id": snapshot_id,
                "pass_name": "header",
                "tables": sorted(header_batch.keys()),
            },
        )
        yield header_batch

        logger.info(
            "json_parse_pass_start",
            extra={"snapshot_id": snapshot_id, "pass_name": "modifier_information"},
        )
        yield from self._parse_modifiers(file_path)

        logger.info(
            "json_parse_pass_start",
            extra={"snapshot_id": snapshot_id, "pass_name": "standard_charge_information"},
        )
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
            for prefix, event, value in ijson.parse(f):
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
                elif prefix == "affirmation.affirmation":
                    h["affirmation"] = value
                elif prefix == "affirmation.confirm_affirmation":
                    h["confirm_affirmation"] = str(value).lower()
                elif prefix == "license_information.state":
                    h["state"] = value
                elif prefix == "license_information.license_number":
                    h["license_number"] = value
                elif prefix == "location_name.item":
                    h.setdefault("location_names", []).append(value)
                elif prefix == "hospital_location.item":
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
            "affirmation": h.get("affirmation"),
            "confirm_affirmation": h.get("confirm_affirmation"),
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
        section = "modifier_information"
        modifiers_rows: list[dict[str, Any]] = []
        modifier_payer_rows: list[dict[str, Any]] = []
        parsed_count = 0

        with _open_maybe_gz(file_path) as f:
            for ordinal, raw_item in enumerate(
                ijson.items(f, "modifier_information.item")
            ):
                try:
                    mi = ModifierInformation.model_validate(raw_item)
                except ValidationError as exc:
                    self._quarantine(section, ordinal, raw_item, exc)
                    continue

                modifier_code_id = f"{snapshot_id}_{ordinal}"
                parsed_count += 1
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

        batch = {
            "modifiers": _df(modifiers_rows, BRONZE_SCHEMAS["modifiers"]),
            "modifier_payer_info": _df(
                modifier_payer_rows, BRONZE_SCHEMAS["modifier_payer_info"]
            ),
        }
        logger.info(
            "json_parse_pass_complete",
            extra={
                "snapshot_id": snapshot_id,
                "pass_name": section,
                "parsed_items": parsed_count,
                "quarantined": self._quarantine_counts.get(section, 0),
                "modifier_rows": len(modifiers_rows),
                "modifier_payer_rows": len(modifier_payer_rows),
            },
        )
        yield batch

    # ------------------------------------------------------------------
    # Pass 3 — standard_charge_information
    # ------------------------------------------------------------------

    def _parse_charges(
        self, file_path: Path
    ) -> Iterator[dict[str, pl.DataFrame]]:
        accumulator: dict[str, list[dict[str, Any]]] = defaultdict(list)
        processed = 0
        batches_emitted = 0
        snapshot_id = self.snapshot_meta["snapshot_id"]
        section = "standard_charge_information"

        with _open_maybe_gz(file_path) as f:
            for item_ordinal, raw_item in enumerate(
                ijson.items(f, "standard_charge_information.item")
            ):
                parsed = self._parse_charge_with_fallback(raw_item)
                if parsed.model is None:
                    diagnostic = self._diagnostic_record(
                        section=section,
                        ordinal=item_ordinal,
                        parsed=parsed,
                        final_status="quarantined",
                    )
                    accumulator["json_record_parse_diagnostics"].append(diagnostic)
                    self._quarantine(
                        section,
                        item_ordinal,
                        raw_item,
                        parsed.errors_by_family,
                        attempted_schema_families=parsed.attempted_schema_families,
                    )
                    continue

                if parsed.used_fallback or parsed.schema_version_mismatch:
                    accumulator["json_record_parse_diagnostics"].append(
                        self._diagnostic_record(
                            section=section,
                            ordinal=item_ordinal,
                            parsed=parsed,
                            final_status="accepted",
                        )
                    )

                flat = self._flatten_sci(parsed.model, item_ordinal, parsed)
                for table_name, rows in flat.items():
                    accumulator[table_name].extend(rows)

                processed += 1
                if processed % BATCH_SIZE == 0:
                    batch = _accumulator_to_batch(accumulator)
                    batches_emitted += 1
                    logger.debug(
                        "json_charge_batch_emitted",
                        extra={
                            "snapshot_id": snapshot_id,
                            "batch_index": batches_emitted,
                            "processed_items": processed,
                            "table_row_counts": {
                                table: len(rows) for table, rows in accumulator.items()
                            },
                        },
                    )
                    yield batch
                    accumulator = defaultdict(list)

        if any(accumulator.values()):
            batch = _accumulator_to_batch(accumulator)
            batches_emitted += 1
            logger.debug(
                "json_charge_batch_emitted",
                extra={
                    "snapshot_id": snapshot_id,
                    "batch_index": batches_emitted,
                    "processed_items": processed,
                    "table_row_counts": {
                        table: len(rows) for table, rows in accumulator.items()
                    },
                },
            )
            yield batch

        logger.info(
            "json_parse_pass_complete",
            extra={
                "snapshot_id": snapshot_id,
                "pass_name": section,
                "parsed_items": processed,
                "batches_emitted": batches_emitted,
                "quarantined": self._quarantine_counts.get(section, 0),
            },
        )

    def _parse_charge_with_fallback(self, raw_item: Any) -> ParsedChargeItem:
        reported_schema_version = self.snapshot_meta.get("schema_version")
        if reported_schema_version is not None:
            reported_schema_version = str(reported_schema_version)
        reported_schema_family = normalize_json_schema_family(reported_schema_version)
        attempt_order = JSON_SCHEMA_ATTEMPT_ORDERS[reported_schema_family]
        errors_by_family: dict[str, dict[str, Any]] = {}

        for schema_family in attempt_order:
            try:
                model = StandardChargeInformation.model_validate(
                    raw_item,
                    context={
                        "schema_family": schema_family,
                        "schema_version": parser_schema_version_for_family(schema_family),
                    },
                )
            except ValidationError as exc:
                errors_by_family[schema_family] = _validation_error_summary(exc)
                continue

            return ParsedChargeItem(
                model=model,
                reported_schema_version=reported_schema_version,
                reported_schema_family=reported_schema_family,
                parser_schema_family=schema_family,
                parser_schema_version=parser_schema_version_for_family(schema_family),
                attempted_schema_families=attempt_order[
                    : attempt_order.index(schema_family) + 1
                ],
                errors_by_family=errors_by_family,
            )

        return ParsedChargeItem(
            model=None,
            reported_schema_version=reported_schema_version,
            reported_schema_family=reported_schema_family,
            parser_schema_family=None,
            parser_schema_version=None,
            attempted_schema_families=attempt_order,
            errors_by_family=errors_by_family,
        )

    def _diagnostic_record(
        self,
        *,
        section: str,
        ordinal: int,
        parsed: ParsedChargeItem,
        final_status: str,
    ) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_meta["snapshot_id"],
            "section": section,
            "record_ordinal": ordinal,
            "reported_schema_version": parsed.reported_schema_version,
            "reported_schema_family": parsed.reported_schema_family,
            "accepted_schema_family": parsed.parser_schema_family,
            "accepted_schema_version": parsed.parser_schema_version,
            "schema_version_mismatch": parsed.schema_version_mismatch,
            "attempted_schema_families": json.dumps(parsed.attempted_schema_families),
            "failure_count": len(parsed.errors_by_family),
            "error_summary": json.dumps(parsed.errors_by_family, default=str),
            "final_status": final_status,
            "diagnosed_at": datetime.now(UTC).isoformat(),
        }

    def _flatten_sci(
        self,
        sci: StandardChargeInformation,
        item_ordinal: int,
        parsed: ParsedChargeItem,
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
                "reported_schema_version": parsed.reported_schema_version,
                "reported_schema_family": parsed.reported_schema_family,
                "parser_schema_family": parsed.parser_schema_family,
                "parser_schema_version": parsed.parser_schema_version,
                "schema_version_mismatch": parsed.schema_version_mismatch,
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
                    "unit": _to_text(sci.drug_information.unit),
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
                    "minimum": _to_text(charge.minimum),
                    "maximum": _to_text(charge.maximum),
                    "gross_charge": _to_text(charge.gross_charge),
                    "discounted_cash": _to_text(charge.discounted_cash),
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
                        "standard_charge_dollar": _to_text(
                            payer.standard_charge_dollar
                        ),
                        "standard_charge_percentage": _to_text(
                            payer.standard_charge_percentage
                        ),
                        "standard_charge_algorithm": payer.standard_charge_algorithm,
                        "estimated_amount": _to_text(payer.estimated_amount),
                        "median_amount": _to_text(payer.median_amount),
                        "tenth_percentile": _to_text(payer.tenth_percentile),
                        "ninetieth_percentile": _to_text(
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
        exc: Exception | dict[str, Any],
        *,
        attempted_schema_families: list[str] | None = None,
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
        if attempted_schema_families is not None:
            record["attempted_schema_families"] = attempted_schema_families
            record["errors_by_schema_family"] = exc
        with q_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

        if not hasattr(self, "_quarantine_counts"):
            self._quarantine_counts = defaultdict(int)
        self._quarantine_counts[section] += 1
        if isinstance(exc, ValidationError):
            err_locs = sorted(
                {
                    ".".join(str(part) for part in err.get("loc", ()))
                    for err in exc.errors()
                }
            )
            logger.debug(
                "validation_error_detail",
                extra={
                    "snapshot_id": snapshot_id,
                    "section": section,
                    "ordinal": ordinal,
                    "error_count": len(exc.errors()),
                    "fields": err_locs[:8],
                },
            )

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


def _validation_error_summary(exc: ValidationError) -> dict[str, Any]:
    """Build a compact, JSON-serializable summary of a Pydantic failure."""
    err_locs = sorted(
        {
            ".".join(str(part) for part in err.get("loc", ()))
            for err in exc.errors()
        }
    )
    return {
        "message": str(exc),
        "error_count": len(exc.errors()),
        "fields": err_locs[:20],
    }


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
            _skip_utf8_bom(f)
            yield f
    else:
        with open(file_path, "rb") as f:
            _skip_utf8_bom(f)
            yield f


def _skip_utf8_bom(f: Any) -> None:
    """Advance past a leading UTF-8 BOM when present."""
    first_bytes = f.read(3)
    if first_bytes != b"\xef\xbb\xbf":
        f.seek(0)
