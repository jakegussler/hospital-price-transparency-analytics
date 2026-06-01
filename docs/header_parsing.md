# MRF Header Parsing — Implementation Guide

Hospital Price Transparency Pipeline
Scope: Bronze layer header extraction for all three source formats
Last updated: 2026-04-19

---

## Overview

Every MRF file — regardless of format — contains two categories of data that must be parsed separately:

1. **File header data** — hospital identity, attestation, licensing, location, and NPI information. Maps to `hospital_mrf_snapshots`, `hospital_locations`, and `type2_npi`.
2. **Charge data** — the actual price information. Maps to `standard_charge_info` / `csv_charge_rows` and their children.

The parser must extract both categories during a single file read. The header fields are folded directly into the `hospital_mrf_snapshots` record alongside the pipeline-generated fields (`snapshot_id`, `file_hash`, `ingested_at`, etc.) — no separate header staging table is created at Bronze. The child tables (`hospital_locations`, `type2_npi`) are populated as rows during the same parsing pass.

---

## CSV File Structure

Both CSV Tall and CSV Wide share the same three-section layout. The charge data begins on **row 4** — the parser must handle the first three rows separately from everything below.

```
Row 1  |  Header keys    (general data element names / column identifiers)
Row 2  |  Header values  (actual hospital metadata values)
Row 3  |  Charge column headers
Row 4+ |  Charge data rows
```

### Row 1 — Header Keys

Row 1 is a standard CSV row where each cell is a field name (or in the case of the attestation, the full attestation statement text itself used as a column header). The template columns are:

| Position | Header Cell Content | Notes |
|---|---|---|
| 1 | `hospital_name` | |
| 2 | `last_updated_on` | |
| 3 | `version` | |
| 4 | `location_name` | Pipe-delimited if multiple locations |
| 5 | `hospital_address` | Pipe-delimited if multiple addresses |
| 6 | `license_number\|[state]` | `[state]` replaced with actual 2-letter state code by the hospital (e.g., `license_number\|TN`) |
| 7 | `type_2_npi` | Pipe-delimited if multiple NPIs |
| 8 | *(full attestation statement text)* | The entire CMS attestation paragraph **is** the column header; the corresponding row 2 value is `true` or `false` |
| 9 | `attester_name` | |
| 10+ | Optional fields (`financial_aid_policy`, `general_contract_provisions`) | Nullable; may not be present. When the `general_contract_provisions` column is present it is emitted as a single row in the `general_contract_provisions` Bronze table (payer/plan null); an absent column emits no row. |

> **Critical parsing note on attestation:** The attestation column header is the full CMS-mandated attestation paragraph. Do not match it by position — match by checking whether a cell starts with `"To the best of its knowledge and belief"`. The corresponding row 2 value in that column is the boolean `true` or `false`.

> **Critical parsing note on license:** The `license_number|[state]` header encodes the state abbreviation in the key itself. Split on `|` to extract `state` from the header key; the corresponding row 2 value is the license number. Example: header cell is `license_number|TN`, so `reported_state = "TN"` and `license_number = <row 2 value>`.

### Row 2 — Header Values

Row 2 contains the actual hospital metadata, aligned positionally with the row 1 keys. Parse row 1 and row 2 together as a key-value zip. Cells may be blank (null) if the hospital did not provide an optional field.

Concrete example of rows 1-2 in a real file:

```
Row 1: hospital_name | last_updated_on | version | location_name | hospital_address | license_number|TN | type_2_npi | [attestation text] | attester_name
Row 2: General Hospital | 2025-01-01    | 3.0.0   | Main Campus   | 123 Main St      | 12345             | 1234567890  | true               | Jane Smith
```

### Row 3 — Charge Column Headers

Row 3 defines the column headers for the charge data section. This row tells the parser what each column in rows 4+ represents.

- **CSV Tall:** Column headers are fixed field names (`payer_name`, `plan_name`, `standard_charge|negotiated_dollar`, etc.).
- **CSV Wide:** Payer-specific column headers embed payer name and plan name directly (e.g., `standard_charge|BlueCross|Blue Choice PPO|negotiated_dollar`). The Wide parser must read row 3 to catalog all payer-bearing columns before reading charge rows.

Row 3 is **not** merged with rows 1-2. It is a separate parsing concern used only to configure the charge data reader.

### Rows 4+ — Charge Data

Standard charge rows, read using the headers extracted from row 3. For Wide files, the payer unpivoting is driven by the column catalog built from row 3.

---

## CSV Header Field to `hospital_mrf_snapshots` Mapping

The parser zips rows 1 and 2 together as `{header_key: value}`, then applies the mapping below. Pipeline-generated fields are merged in at ingestion time from the metadata subfolder.

| `hospital_mrf_snapshots` Column | Source | Extraction Logic |
|---|---|---|
| `snapshot_id` | Pipeline-generated | UUID or hash assigned at ingestion time |
| `hospital_id` | Pipeline-generated | Null at Bronze; resolved at Silver |
| `source_url` | Pipeline-generated | From metadata subfolder |
| `source_file_name` | Pipeline-generated | From metadata subfolder |
| `source_format` | Pipeline-generated | `csv_tall` or `csv_wide` |
| `file_hash` | Pipeline-generated | SHA-256 of raw file bytes; from metadata subfolder |
| `ingested_at` | Pipeline-generated | UTC timestamp at parse time |
| `is_current_snapshot` | Pipeline-generated | Set by ingestion controller |
| `valid_from` | Pipeline-generated | Set by ingestion controller |
| `valid_to` | Pipeline-generated | Null at Bronze |
| `reported_hospital_name` | Row 1-2 | Key: `hospital_name` |
| `published_last_updated_on` | Row 1-2 | Key: `last_updated_on`; stored as `pa.string()` to tolerate non-ISO-8601 values |
| `schema_version` | Row 1-2 | Key: `version` |
| `attestation` | Row 1 | The column header text that starts with `"To the best of its knowledge and belief"` |
| `confirm_attestation` | Row 2 | The value in the attestation column (`"true"` or `"false"`) |
| `attester_name` | Row 1-2 | Key: `attester_name` |
| `reported_state` | Row 1 header key | Split `license_number\|TN` on `\|`; take index `[1]` |
| `license_number` | Row 2 | Value in the `license_number\|[state]` column |

> **On `attestation` vs `confirm_attestation`:** In CSV, the attestation statement text is the column header (row 1), and `true`/`false` is the column value (row 2). Store the full statement text in `attestation` and the boolean string in `confirm_attestation`. This mirrors the JSON schema which separates them as `attestation.attestation` and `attestation.confirm_attestation`.

---

## CSV Header Field to Child Table Mapping

These fields contain pipe-delimited lists and are exploded into child table rows during the same parsing pass as the snapshot record.

### `hospital_locations`

| Column | Source | Notes |
|---|---|---|
| `snapshot_id` | Pipeline-generated | |
| `location_ordinal` | Parser-generated | 0-based position after splitting on `\|` |
| `location_name` | Row 1-2, key `location_name` | Split on `\|`; zip by position with `hospital_address` values |
| `hospital_address` | Row 1-2, key `hospital_address` | Split on `\|`; zip by position with `location_name` values |

If only one location exists, the value is not pipe-delimited — treat as a single-element list. If `location_name` and `hospital_address` produce different counts after splitting, log a data quality warning and zip to the shorter length.

### `type2_npi`

| Column | Source | Notes |
|---|---|---|
| `snapshot_id` | Pipeline-generated | |
| `npi_ordinal` | Parser-generated | 0-based position after splitting on `\|` |
| `npi` | Row 1-2, key `type_2_npi` | Split on `\|`; strip whitespace; drop empty strings |

---

## CSV Parsing Pseudocode

```python
def parse_csv_header(file_path: str, snapshot_meta: dict) -> tuple[dict, list, list]:
    """
    Parses rows 1-2 of a CMS MRF CSV file (Tall or Wide).

    Returns:
        snapshot_record  -- dict matching hospital_mrf_snapshots schema
        location_rows    -- list of dicts matching hospital_locations schema
        npi_rows         -- list of dicts matching type2_npi schema
    """
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        row1 = next(reader)  # header keys
        row2 = next(reader)  # header values
        # row 3 is charge column headers -- consumed separately by charge parser

    # Zip rows 1 and 2 into a key-value dict
    header = dict(zip(row1, row2))

    # Attestation: header key IS the statement text; row 2 value is true/false
    attestation_text = None
    confirm_attestation = None
    for key in header:
        if key.strip().startswith("To the best of its knowledge and belief"):
            attestation_text = key.strip()
            confirm_attestation = header[key].strip()  # store as string "true"/"false"
            break

    # License: state is encoded in the header key itself
    reported_state = None
    license_number = None
    for key in header:
        if key.startswith("license_number|"):
            parts = key.split("|")
            reported_state = parts[1].strip() if len(parts) > 1 else None
            license_number = header[key].strip() or None
            break

    snapshot_record = {
        **snapshot_meta,  # pipeline-generated fields from metadata subfolder
        "reported_hospital_name":    header.get("hospital_name", "").strip() or None,
        "published_last_updated_on": header.get("last_updated_on", "").strip() or None,
        "schema_version":            header.get("version", "").strip() or None,
        "attestation":               attestation_text,
        "confirm_attestation":       confirm_attestation,
        "attester_name":             header.get("attester_name", "").strip() or None,
        "reported_state":            reported_state,
        "license_number":            license_number,
    }

    # hospital_locations: zip pipe-delimited parallel lists
    location_names = [v.strip() for v in header.get("location_name", "").split("|")]
    hospital_addrs = [v.strip() for v in header.get("hospital_address", "").split("|")]
    n_locations = max(len(location_names), len(hospital_addrs))
    location_rows = [
        {
            "snapshot_id":      snapshot_meta["snapshot_id"],
            "location_ordinal": i,
            "location_name":    location_names[i] if i < len(location_names) else None,
            "hospital_address": hospital_addrs[i] if i < len(hospital_addrs) else None,
        }
        for i in range(n_locations)
    ]

    # type2_npi: split pipe-delimited string
    npis = [v.strip() for v in header.get("type_2_npi", "").split("|") if v.strip()]
    npi_rows = [
        {"snapshot_id": snapshot_meta["snapshot_id"], "npi_ordinal": i, "npi": npi}
        for i, npi in enumerate(npis)
    ]

    return snapshot_record, location_rows, npi_rows


def get_charge_reader(file_path: str):
    """
    Returns a CSV reader positioned at row 4 (first charge data row),
    with row 3 column headers already consumed and returned separately.
    Caller is responsible for closing the returned file handle.
    """
    f = open(file_path, newline="", encoding="utf-8-sig")
    reader = csv.reader(f)
    next(reader)  # row 1 -- already consumed by parse_csv_header
    next(reader)  # row 2 -- already consumed by parse_csv_header
    charge_headers = next(reader)  # row 3 -- charge column headers
    return reader, charge_headers, f
```

---

## JSON File Structure

The CMS MRF JSON schema is a single top-level object. All hospital header fields are top-level keys on the root object. The charge data is in the `standard_charge_information` array. There is no row-splitting concern — but because MRF JSON files for large hospital systems can exceed several gigabytes, `json.load()` is not appropriate. The header is streamed with `ijson` and parsing stops before `standard_charge_information` begins.

```
{
    "hospital_name":              string,
    "last_updated_on":            string (ISO 8601 date),
    "version":                    string,
    "location_name":              [ string, ... ],
    "hospital_address":           [ string, ... ],
    "type_2_npi":                 [ string, ... ],
    "license_information":        { "license_number": string, "state": string },
    "attestation": {
        "attestation":            string  (full statement text),
        "confirm_attestation":    boolean,
        "attester_name":          string
    },
    "standard_charge_information": [ ... ],   <- charge data; streamed separately
    "modifier_information":        [ ... ]    <- modifier definitions; optional
}
```

The `modifier_information` array is also top-level and must be fully read before `standard_charge_information` begins (or in a second pass), since it defines the modifier dimension rows that `standard_charge_modifiers` will reference at Silver.

---

## JSON Header Field to `hospital_mrf_snapshots` Mapping

| `hospital_mrf_snapshots` Column | JSON Path | Notes |
|---|---|---|
| `snapshot_id` | Pipeline-generated | |
| `hospital_id` | Pipeline-generated | Null at Bronze |
| `source_url` | Pipeline-generated | |
| `source_file_name` | Pipeline-generated | |
| `source_format` | Pipeline-generated | `"json"` |
| `file_hash` | Pipeline-generated | |
| `ingested_at` | Pipeline-generated | |
| `is_current_snapshot` | Pipeline-generated | |
| `valid_from` | Pipeline-generated | |
| `valid_to` | Pipeline-generated | Null at Bronze |
| `reported_hospital_name` | `hospital_name` | |
| `published_last_updated_on` | `last_updated_on` | Stored as `pa.string()` |
| `schema_version` | `version` | |
| `attestation` | `attestation.attestation` | Full statement text |
| `confirm_attestation` | `attestation.confirm_attestation` | Boolean in JSON; store as string `"true"`/`"false"` for type consistency with CSV |
| `attester_name` | `attestation.attester_name` | |
| `reported_state` | `license_information.state` | |
| `license_number` | `license_information.license_number` | Nullable per schema |

---

## JSON Header Field to Child Table Mapping

### `hospital_locations`

The JSON schema stores `location_name` and `hospital_address` as parallel arrays. Zip them by index, exactly as with the pipe-delimited CSV values.

| Column | JSON Path | Notes |
|---|---|---|
| `snapshot_id` | Pipeline-generated | |
| `location_ordinal` | Array index (0-based) | |
| `location_name` | `location_name[i]` | |
| `hospital_address` | `hospital_address[i]` | |

### `type2_npi`

| Column | JSON Path | Notes |
|---|---|---|
| `snapshot_id` | Pipeline-generated | |
| `npi_ordinal` | Array index (0-based) | |
| `npi` | `type_2_npi[i]` | |

---

## JSON Parsing Pseudocode

```python
def parse_json_header(file_path: str, snapshot_meta: dict) -> tuple[dict, list, list]:
    """
    Streams the top-level header fields from a CMS MRF JSON file using ijson.
    Stops streaming before standard_charge_information to avoid loading the full file.

    Returns:
        snapshot_record  -- dict matching hospital_mrf_snapshots schema
        location_rows    -- list of dicts matching hospital_locations schema
        npi_rows         -- list of dicts matching type2_npi schema
    """
    import ijson

    h = {}  # accumulator for header fields

    with open(file_path, "rb") as f:
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
                # ijson yields booleans natively; convert to string for Bronze type consistency
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
            elif prefix == "standard_charge_information" and event == "start_array":
                break  # header is complete; charge data handled by charge parser

    snapshot_record = {
        **snapshot_meta,
        "reported_hospital_name":    h.get("hospital_name"),
        "published_last_updated_on": h.get("last_updated_on"),
        "schema_version":            h.get("version"),
        "attestation":               h.get("attestation_text"),
        "confirm_attestation":       h.get("confirm_attestation"),
        "attester_name":             h.get("attester_name"),
        "reported_state":            h.get("state"),
        "license_number":            h.get("license_number"),
    }

    location_names = h.get("location_names", [])
    hospital_addrs = h.get("hospital_addresses", [])
    n_locations = max(len(location_names), len(hospital_addrs), 1)
    location_rows = [
        {
            "snapshot_id":      snapshot_meta["snapshot_id"],
            "location_ordinal": i,
            "location_name":    location_names[i] if i < len(location_names) else None,
            "hospital_address": hospital_addrs[i] if i < len(hospital_addrs) else None,
        }
        for i in range(n_locations)
    ]

    npi_rows = [
        {"snapshot_id": snapshot_meta["snapshot_id"], "npi_ordinal": i, "npi": npi}
        for i, npi in enumerate(h.get("type_2_npis", []))
    ]

    return snapshot_record, location_rows, npi_rows
```

> **Why `ijson` and not `json.load()`:** MRF JSON files for large hospital systems can exceed several gigabytes. `json.load()` loads the entire document into memory before returning. The `ijson` approach reads the file as a token stream and stops at `standard_charge_information`, meaning the header parse completes after reading only the first few kilobytes regardless of total file size. The charge parser then opens the file in a second pass and streams `standard_charge_information.item` objects one at a time via `ijson.items()`.

---

## How Header Data Joins With `hospital_mrf_snapshots`

There is no join. The header fields **are** the snapshot record. The parser merges two dicts — pipeline-generated metadata and source-derived header values — and writes one row to `hospital_mrf_snapshots`.

```
snapshot_meta dict                    file header dict
(pipeline-generated)                  (source-derived)
--------------------------            --------------------------
snapshot_id                           reported_hospital_name
hospital_id (null)                    published_last_updated_on
source_url                  merge     schema_version
source_file_name           ------->   attestation
source_format              one dict   confirm_attestation
file_hash                             attester_name
ingested_at                           reported_state
is_current_snapshot                   license_number
valid_from
valid_to (null)
                 |
                 v
    hospital_mrf_snapshots  (one row written per ingested file)
                 |
                 |-- hospital_locations  (one row per location; FK: snapshot_id)
                 |-- type2_npi           (one row per NPI; FK: snapshot_id)
```

The child tables are written in the same transaction as the snapshot row. No downstream join at Bronze is required — any query needing location or NPI data joins to those tables via `snapshot_id`.

---

## Format Comparison Summary

| Concern | CSV Tall | CSV Wide | JSON |
|---|---|---|---|
| Header location | Rows 1-2 | Rows 1-2 | Top-level JSON keys |
| Charge data start | Row 4 | Row 4 | `standard_charge_information[]` |
| Charge column headers | Row 3 (fixed names) | Row 3 (payer names embedded in headers) | None; structure is defined by JSON schema |
| Attestation text location | Row 1 column header | Row 1 column header | `attestation.attestation` |
| Attestation boolean location | Row 2 value | Row 2 value | `attestation.confirm_attestation` |
| State encoding | In row 1 key: `license_number\|TN` | Same as Tall | `license_information.state` |
| License number | Row 2 value in that column | Same as Tall | `license_information.license_number` |
| Multi-location encoding | Pipe-delimited in row 2 | Same as Tall | Parallel arrays `location_name[]`, `hospital_address[]` |
| Multi-NPI encoding | Pipe-delimited in row 2 | Same as Tall | Array `type_2_npi[]` |
| Modifier definitions | Not present | Not present | Top-level `modifier_information[]` |
| Memory risk during header parse | None; rows 1-3 are tiny | None | Use `ijson`; stop before `standard_charge_information` |
