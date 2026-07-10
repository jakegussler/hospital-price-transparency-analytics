"""Export the public Evidence.dev presentation artifact.

The public presentation layer intentionally sees only the allowlisted Gold BI
marts. It never receives the working DuckDB warehouse, Silver/Bronze tables, or
Gold atomic fact tables.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class EvidenceExportSpec:
    """One public table exported for Evidence."""

    public_name: str
    source_schema: str
    source_table: str

    @property
    def source_relation(self) -> str:
        return f"{self.source_schema}.{self.source_table}"

    @property
    def parquet_name(self) -> str:
        return f"{self.public_name}.parquet"


EVIDENCE_EXPORTS: tuple[EvidenceExportSpec, ...] = (
    EvidenceExportSpec(
        public_name="hospital_overview",
        source_schema="main_gold",
        source_table="gld_bi__hospital_overview",
    ),
    EvidenceExportSpec(
        public_name="service_market_explorer",
        source_schema="main_gold",
        source_table="gld_bi__service_market_explorer",
    ),
    EvidenceExportSpec(
        public_name="hospital_service_rankings",
        source_schema="main_gold",
        source_table="gld_bi__hospital_service_rankings",
    ),
    EvidenceExportSpec(
        public_name="payer_contracting_explorer",
        source_schema="main_gold",
        source_table="gld_bi__payer_contracting_explorer",
    ),
    EvidenceExportSpec(
        public_name="comparison_blocker_summary",
        source_schema="main_gold",
        source_table="gld_bi__comparison_blocker_summary",
    ),
    EvidenceExportSpec(
        public_name="featured_services",
        source_schema="main_gold",
        source_table="gld_bi__featured_services",
    ),
    EvidenceExportSpec(
        public_name="market_summary",
        source_schema="main_gold",
        source_table="gld_bi__market_summary",
    ),
    EvidenceExportSpec(
        public_name="comparability_funnel",
        source_schema="main_gold",
        source_table="gld_bi__comparability_funnel",
    ),
    EvidenceExportSpec(
        public_name="payer_overview",
        source_schema="main_gold",
        source_table="gld_bi__payer_overview",
    ),
)

PUBLIC_METADATA_NAME = "public_metadata.parquet"
PUBLIC_DATA_DICTIONARY_NAME = "public_data_dictionary.parquet"
DEFAULT_CORPUS_LABEL = "Nashville metro"

# Download-bundle CSVs larger than this are shipped gzip-compressed
# (<name>.csv.gz) so a single wide mart cannot bloat the static site artifact.
CSV_GZIP_THRESHOLD_BYTES = 25 * 1024 * 1024

# Columns of the generated artifacts themselves, so the public data dictionary
# also documents public_metadata and public_data_dictionary.
_GENERATED_ARTIFACT_DICTIONARY_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "exported_at_utc",
        "UTC timestamp when the public artifact was exported.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "corpus_label",
        "Human-readable label of the loaded hospital corpus (the scope of every claim).",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "build_id",
        "Source-repository build identifier (git commit) of the export, when available.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "public_table_name",
        "Public name of the exported table.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "source_schema",
        "Warehouse schema the table was exported from.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "source_table",
        "Warehouse table the export was read from.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "row_count",
        "Rows exported for the table.",
    ),
    (
        "public_metadata",
        "generated",
        "One row per exported public table: export provenance and row counts.",
        "csv_file_name",
        "File name of the table's CSV in the download bundle "
        "(gzip-compressed for large tables); null when no bundle was produced.",
    ),
    (
        "public_data_dictionary",
        "generated",
        "One row per public table column: plain-language column documentation.",
        "public_table_name",
        "Public name of the documented table.",
    ),
    (
        "public_data_dictionary",
        "generated",
        "One row per public table column: plain-language column documentation.",
        "source_table",
        "Warehouse (dbt) model behind the table.",
    ),
    (
        "public_data_dictionary",
        "generated",
        "One row per public table column: plain-language column documentation.",
        "table_description",
        "Plain-language description of the table, including its grain.",
    ),
    (
        "public_data_dictionary",
        "generated",
        "One row per public table column: plain-language column documentation.",
        "column_name",
        "Documented column name.",
    ),
    (
        "public_data_dictionary",
        "generated",
        "One row per public table column: plain-language column documentation.",
        "column_description",
        "Plain-language description of the column.",
    ),
)

DISALLOWED_EVIDENCE_SQL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("main_gold", re.compile(r"(?<![A-Za-z0-9_])main_gold(?![A-Za-z0-9_])", re.I)),
    ("gld_fct__", re.compile(r"(?<![A-Za-z0-9_])gld_fct__", re.I)),
    ("gld_bridge__", re.compile(r"(?<![A-Za-z0-9_])gld_bridge__", re.I)),
    ("slv_", re.compile(r"(?<![A-Za-z0-9_])slv_", re.I)),
    ("brz_", re.compile(r"(?<![A-Za-z0-9_])brz_", re.I)),
    ("val__", re.compile(r"(?<![A-Za-z0-9_])val__", re.I)),
    ("val_int__", re.compile(r"(?<![A-Za-z0-9_])val_int__", re.I)),
    ("raw", re.compile(r"(?<![A-Za-z0-9_])raw(?![A-Za-z0-9_])", re.I)),
    ("bronze", re.compile(r"(?<![A-Za-z0-9_])bronze(?![A-Za-z0-9_])", re.I)),
    ("quarantine", re.compile(r"(?<![A-Za-z0-9_])quarantine(?![A-Za-z0-9_])", re.I)),
)


class EvidenceExportError(RuntimeError):
    """Raised when a public Evidence export cannot be produced safely."""


@dataclass(frozen=True)
class EvidenceSqlViolation:
    """A disallowed SQL reference found in an Evidence source or page."""

    path: Path
    token: str
    line_number: int
    line: str


@dataclass(frozen=True)
class EvidenceReadinessRule:
    """Minimum row-count expectation for a public-demo Evidence mart."""

    public_name: str
    min_rows: int = 1


@dataclass(frozen=True)
class EvidenceReadinessIssue:
    """A BI mart failed an optional public-demo readiness rule."""

    public_name: str
    source_relation: str
    row_count: int
    min_rows: int

    @property
    def message(self) -> str:
        return (
            f"{self.source_relation} has {self.row_count} rows; "
            f"expected at least {self.min_rows} for Evidence readiness."
        )


DEFAULT_EVIDENCE_READINESS_RULES: tuple[EvidenceReadinessRule, ...] = (
    EvidenceReadinessRule("hospital_overview"),
    EvidenceReadinessRule("service_market_explorer"),
    EvidenceReadinessRule("featured_services"),
    EvidenceReadinessRule("market_summary"),
    EvidenceReadinessRule("comparability_funnel"),
)


def export_evidence_artifact(
    *,
    source_duckdb: Path,
    target_dir: Path,
    replace: bool = False,
    corpus_label: str = DEFAULT_CORPUS_LABEL,
    exported_at: datetime | None = None,
    compute_source_hash: bool = True,
    build_id: str | None = None,
    dictionary_yml: Path | None = None,
    downloads_dir: Path | None = None,
    csv_gzip_threshold_bytes: int = CSV_GZIP_THRESHOLD_BYTES,
) -> dict[str, int]:
    """Export allowlisted Gold BI marts to Parquet files for Evidence.

    When ``dictionary_yml`` is provided, a ``public_data_dictionary.parquet``
    generated from the dbt schema yml is written beside the mart Parquet files.
    When ``downloads_dir`` is provided, a public download bundle (Parquet + CSV
    per mart, the data dictionary as CSV, and a generated README) is atomically
    swapped into that directory for the Evidence static file surface.

    Returns row counts keyed by public table name.
    """

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - exercised only without warehouse extra
        raise EvidenceExportError(
            "duckdb is required; install with the warehouse extra before exporting Evidence data."
        ) from exc

    source_duckdb = source_duckdb.expanduser()
    target_dir = target_dir.expanduser()
    exported_at = exported_at or datetime.now(UTC)

    if not source_duckdb.exists():
        raise EvidenceExportError(f"Source DuckDB does not exist: {source_duckdb}")
    if target_dir.exists() and any(target_dir.iterdir()) and not replace:
        raise EvidenceExportError(
            f"Target directory is not empty: {target_dir}. Pass --replace to swap it."
        )

    dictionary_rows: list[tuple[str, str, str, str, str]] | None = None
    if dictionary_yml is not None:
        dictionary_rows = _load_dictionary_rows(dictionary_yml)

    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = parent / f".{target_dir.name}.tmp-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)

    downloads_temp_dir: Path | None = None
    try:
        source_stats = _source_database_stats(source_duckdb, compute_hash=compute_source_hash)
        with duckdb.connect(str(source_duckdb), read_only=True) as con:
            row_counts = _export_allowlisted_tables(con, temp_dir)
            if dictionary_rows is not None:
                _write_public_data_dictionary(
                    con=con,
                    temp_dir=temp_dir,
                    dictionary_rows=dictionary_rows,
                )
            csv_file_names: dict[str, str] | None = None
            if downloads_dir is not None:
                downloads_dir = downloads_dir.expanduser()
                downloads_dir.parent.mkdir(parents=True, exist_ok=True)
                downloads_temp_dir = (
                    downloads_dir.parent / f".{downloads_dir.name}.tmp-{uuid.uuid4().hex}"
                )
                downloads_temp_dir.mkdir(parents=True)
                csv_file_names = _write_downloads_bundle(
                    con=con,
                    temp_dir=temp_dir,
                    downloads_temp_dir=downloads_temp_dir,
                    row_counts=row_counts,
                    corpus_label=corpus_label,
                    exported_at=exported_at,
                    build_id=build_id,
                    include_dictionary=dictionary_rows is not None,
                    csv_gzip_threshold_bytes=csv_gzip_threshold_bytes,
                )
            _write_public_metadata(
                con=con,
                temp_dir=temp_dir,
                row_counts=row_counts,
                corpus_label=corpus_label,
                exported_at=exported_at,
                source_stats=source_stats,
                build_id=build_id,
                csv_file_names=csv_file_names,
            )

        if target_dir.exists():
            if replace:
                shutil.rmtree(target_dir)
            else:
                target_dir.rmdir()
        temp_dir.replace(target_dir)

        if downloads_temp_dir is not None and downloads_dir is not None:
            if downloads_dir.exists():
                shutil.rmtree(downloads_dir)
            downloads_temp_dir.replace(downloads_dir)

        return row_counts
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if downloads_temp_dir is not None:
            shutil.rmtree(downloads_temp_dir, ignore_errors=True)
        raise


def scan_evidence_sql(root: Path) -> list[EvidenceSqlViolation]:
    """Find disallowed executable SQL references under an Evidence app root."""

    root = root.expanduser()
    if not root.exists():
        return []

    violations: list[EvidenceSqlViolation] = []
    candidates = sorted(
        path
        for pattern in ("*.sql", "*.md")
        for path in root.rglob(pattern)
        if "node_modules" not in path.parts
        and "build" not in path.parts
        and ".evidence" not in path.parts
    )

    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".sql":
            sql_blocks = [(1, _strip_sql_comments(text))]
        else:
            sql_blocks = _extract_markdown_sql_blocks(text)

        for block_start, block_text in sql_blocks:
            for token, pattern in DISALLOWED_EVIDENCE_SQL_PATTERNS:
                for match in pattern.finditer(block_text):
                    line_number, line = _line_for_offset(block_text, match.start(), block_start)
                    violations.append(
                        EvidenceSqlViolation(
                            path=path,
                            token=token,
                            line_number=line_number,
                            line=line.strip(),
                        )
                    )

    return violations


def check_evidence_readiness(
    *,
    source_duckdb: Path,
    rules: tuple[EvidenceReadinessRule, ...] = DEFAULT_EVIDENCE_READINESS_RULES,
) -> list[EvidenceReadinessIssue]:
    """Check optional row-count gates for a public-demo Evidence corpus.

    This is intentionally separate from export_evidence_artifact(): smoke runs
    with tiny corpora should still be able to export schema-valid empty marts,
    while publication/demo builds can opt into stricter row-count expectations.
    """

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - exercised only without warehouse extra
        raise EvidenceExportError(
            "duckdb is required; install with the warehouse extra before checking Evidence data."
        ) from exc

    source_duckdb = source_duckdb.expanduser()
    if not source_duckdb.exists():
        raise EvidenceExportError(f"Source DuckDB does not exist: {source_duckdb}")

    specs_by_public_name = {spec.public_name: spec for spec in EVIDENCE_EXPORTS}
    issues: list[EvidenceReadinessIssue] = []

    with duckdb.connect(str(source_duckdb), read_only=True) as con:
        for rule in rules:
            try:
                spec = specs_by_public_name[rule.public_name]
            except KeyError as exc:
                raise EvidenceExportError(
                    f"Unknown Evidence public table in readiness rule: {rule.public_name}"
                ) from exc

            _assert_relation_exists(con, spec)
            row_count = int(
                con.execute(f"select count(*) from {_quote_relation(spec)}").fetchone()[0]
            )
            if row_count < rule.min_rows:
                issues.append(
                    EvidenceReadinessIssue(
                        public_name=spec.public_name,
                        source_relation=spec.source_relation,
                        row_count=row_count,
                        min_rows=rule.min_rows,
                    )
                )

    return issues


def assert_evidence_readiness(
    *,
    source_duckdb: Path,
    rules: tuple[EvidenceReadinessRule, ...] = DEFAULT_EVIDENCE_READINESS_RULES,
) -> None:
    """Raise EvidenceExportError when optional Evidence readiness checks fail."""

    issues = check_evidence_readiness(source_duckdb=source_duckdb, rules=rules)
    if issues:
        messages = "\n".join(f"- {issue.message}" for issue in issues)
        raise EvidenceExportError(f"Evidence readiness checks failed:\n{messages}")


def _export_allowlisted_tables(con: object, temp_dir: Path) -> dict[str, int]:
    row_counts: dict[str, int] = {}

    for spec in EVIDENCE_EXPORTS:
        _assert_relation_exists(con, spec)
        row_count = int(con.execute(f"select count(*) from {_quote_relation(spec)}").fetchone()[0])
        row_counts[spec.public_name] = row_count

        output_path = temp_dir / spec.parquet_name
        con.execute(
            f"copy (select * from {_quote_relation(spec)}) to ? (format parquet)",
            [str(output_path)],
        )

    return row_counts


def _assert_relation_exists(con: object, spec: EvidenceExportSpec) -> None:
    exists = con.execute(
        """
        select count(*)
        from information_schema.tables
        where table_schema = ?
          and table_name = ?
        """,
        [spec.source_schema, spec.source_table],
    ).fetchone()[0]
    if exists == 0:
        raise EvidenceExportError(f"Required BI mart is missing: {spec.source_relation}")


def _write_public_metadata(
    *,
    con: object,
    temp_dir: Path,
    row_counts: dict[str, int],
    corpus_label: str,
    exported_at: datetime,
    source_stats: dict[str, object],
    build_id: str | None = None,
    csv_file_names: dict[str, str] | None = None,
) -> None:
    metadata_rows = [
        (
            exported_at.isoformat(),
            corpus_label,
            build_id,
            spec.public_name,
            spec.source_schema,
            spec.source_table,
            row_counts[spec.public_name],
            (csv_file_names or {}).get(spec.public_name),
            source_stats["size_bytes"],
            source_stats["mtime_utc"],
            source_stats["sha256"],
        )
        for spec in EVIDENCE_EXPORTS
    ]
    metadata_path = temp_dir / PUBLIC_METADATA_NAME
    con.execute(
        """
        create temporary table evidence_public_metadata (
            exported_at_utc varchar,
            corpus_label varchar,
            build_id varchar,
            public_table_name varchar,
            source_schema varchar,
            source_table varchar,
            row_count bigint,
            csv_file_name varchar,
            source_database_size_bytes bigint,
            source_database_mtime_utc varchar,
            source_database_sha256 varchar
        )
        """
    )
    con.executemany(
        """
        insert into evidence_public_metadata values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        metadata_rows,
    )
    con.execute(
        """
        copy evidence_public_metadata
        to '{path}'
        (format parquet)
        """.format(path=_sql_string_literal(metadata_path)),
    )


def _load_dictionary_rows(dictionary_yml: Path) -> list[tuple[str, str, str, str, str]]:
    """Parse the Gold BI dbt schema yml into public data-dictionary rows.

    Only models on the export allowlist are included, keyed by their public
    names, so the public dictionary never documents non-public tables. Rows for
    the generated public_metadata/public_data_dictionary artifacts are appended
    so the dictionary is self-describing.
    """

    import yaml

    dictionary_yml = dictionary_yml.expanduser()
    if not dictionary_yml.exists():
        raise EvidenceExportError(f"Data dictionary schema yml does not exist: {dictionary_yml}")

    parsed = yaml.safe_load(dictionary_yml.read_text(encoding="utf-8")) or {}
    models = {
        model.get("name"): model for model in parsed.get("models", []) if isinstance(model, dict)
    }

    public_by_source = {spec.source_table: spec for spec in EVIDENCE_EXPORTS}
    rows: list[tuple[str, str, str, str, str]] = []
    for source_table, spec in public_by_source.items():
        model = models.get(source_table)
        if model is None:
            raise EvidenceExportError(
                f"Data dictionary yml is missing model documentation: {source_table}"
            )
        table_description = _normalize_yaml_text(model.get("description"))
        for column in model.get("columns", []):
            if not isinstance(column, dict) or not column.get("name"):
                continue
            rows.append(
                (
                    spec.public_name,
                    source_table,
                    table_description,
                    str(column["name"]),
                    _normalize_yaml_text(column.get("description")),
                )
            )

    rows.extend(_GENERATED_ARTIFACT_DICTIONARY_ROWS)
    return rows


def _normalize_yaml_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _write_public_data_dictionary(
    *,
    con: object,
    temp_dir: Path,
    dictionary_rows: list[tuple[str, str, str, str, str]],
) -> None:
    dictionary_path = temp_dir / PUBLIC_DATA_DICTIONARY_NAME
    con.execute(
        """
        create temporary table evidence_public_data_dictionary (
            public_table_name varchar,
            source_table varchar,
            table_description varchar,
            column_name varchar,
            column_description varchar
        )
        """
    )
    con.executemany(
        "insert into evidence_public_data_dictionary values (?, ?, ?, ?, ?)",
        dictionary_rows,
    )
    con.execute(
        """
        copy evidence_public_data_dictionary
        to '{path}'
        (format parquet)
        """.format(path=_sql_string_literal(dictionary_path)),
    )


def _write_downloads_bundle(
    *,
    con: object,
    temp_dir: Path,
    downloads_temp_dir: Path,
    row_counts: dict[str, int],
    corpus_label: str,
    exported_at: datetime,
    build_id: str | None,
    include_dictionary: bool,
    csv_gzip_threshold_bytes: int = CSV_GZIP_THRESHOLD_BYTES,
) -> dict[str, str]:
    """Write the public download bundle: Parquet + CSV per mart plus a README.

    Files come from the already-exported temp artifacts (Parquet copied as-is,
    CSV converted with DuckDB) so the bundle always matches the site's data.
    CSVs larger than ``csv_gzip_threshold_bytes`` are replaced by a
    gzip-compressed ``.csv.gz``. Returns the CSV file name per public table.
    """

    csv_file_names: dict[str, str] = {}
    for spec in EVIDENCE_EXPORTS:
        source_parquet = temp_dir / spec.parquet_name
        shutil.copyfile(source_parquet, downloads_temp_dir / spec.parquet_name)
        csv_file_names[spec.public_name] = _parquet_to_csv(
            con,
            source_parquet,
            downloads_temp_dir / f"{spec.public_name}.csv",
            gzip_threshold_bytes=csv_gzip_threshold_bytes,
        )

    if include_dictionary:
        source_dictionary = temp_dir / PUBLIC_DATA_DICTIONARY_NAME
        shutil.copyfile(source_dictionary, downloads_temp_dir / PUBLIC_DATA_DICTIONARY_NAME)
        _parquet_to_csv(
            con,
            source_dictionary,
            downloads_temp_dir / "public_data_dictionary.csv",
            gzip_threshold_bytes=csv_gzip_threshold_bytes,
        )

    readme_path = downloads_temp_dir / "README.md"
    readme_path.write_text(
        _downloads_readme_text(
            row_counts=row_counts,
            corpus_label=corpus_label,
            exported_at=exported_at,
            build_id=build_id,
            include_dictionary=include_dictionary,
            csv_file_names=csv_file_names,
        ),
        encoding="utf-8",
    )
    return csv_file_names


def _parquet_to_csv(
    con: object,
    parquet_path: Path,
    csv_path: Path,
    *,
    gzip_threshold_bytes: int = CSV_GZIP_THRESHOLD_BYTES,
) -> str:
    """Convert a Parquet artifact to CSV; gzip-compress when it is large.

    Returns the file name actually written (``x.csv`` or ``x.csv.gz``).
    """

    con.execute(
        """
        copy (select * from read_parquet('{source}'))
        to '{target}'
        (format csv, header)
        """.format(
            source=_sql_string_literal(parquet_path),
            target=_sql_string_literal(csv_path),
        )
    )
    if csv_path.stat().st_size <= gzip_threshold_bytes:
        return csv_path.name

    gzip_path = csv_path.with_name(csv_path.name + ".gz")
    con.execute(
        """
        copy (select * from read_parquet('{source}'))
        to '{target}'
        (format csv, header, compression gzip)
        """.format(
            source=_sql_string_literal(parquet_path),
            target=_sql_string_literal(gzip_path),
        )
    )
    csv_path.unlink()
    return gzip_path.name


def _downloads_readme_text(
    *,
    row_counts: dict[str, int],
    corpus_label: str,
    exported_at: datetime,
    build_id: str | None,
    include_dictionary: bool,
    csv_file_names: dict[str, str] | None = None,
) -> str:
    csv_file_names = csv_file_names or {}
    table_lines = "\n".join(
        f"- `{spec.public_name}` ({row_counts[spec.public_name]} rows): "
        f"`{spec.parquet_name}` / "
        f"`{csv_file_names.get(spec.public_name, spec.public_name + '.csv')}`, "
        f"exported from `{spec.source_table}`."
        for spec in EVIDENCE_EXPORTS
    )
    dictionary_line = (
        "- `public_data_dictionary` documents every table and column in this bundle.\n"
        if include_dictionary
        else ""
    )
    build_line = f"Build: `{build_id}`\n" if build_id else ""
    return (
        "# Hospital Price Transparency — Public Data Bundle\n"
        "\n"
        f"Corpus: {corpus_label}\n"
        f"Exported (UTC): {exported_at.isoformat()}\n"
        f"{build_line}"
        "\n"
        "Each table ships as Parquet and CSV with identical content. CSVs\n"
        "larger than 25 MB are gzip-compressed (`.csv.gz`).\n"
        "\n"
        f"{table_lines}\n"
        f"{dictionary_line}"
        "\n"
        "## How to use this data responsibly\n"
        "\n"
        "- Every claim is bounded to the corpus above. Do not present results\n"
        "  as regional or national benchmarks beyond it.\n"
        "- Never rank different price types against each other: gross_charge\n"
        "  (list price), discounted_cash (self-pay), and negotiated_dollar\n"
        "  (insurer-negotiated) are separate measures.\n"
        "- Respect the published comparison gates: rows or contexts marked\n"
        "  insufficient_denominator have fewer than 3 reporting hospitals and\n"
        "  carry no market statistics by design.\n"
        "- Readiness/usability scores describe how usable a hospital's\n"
        "  published file is. They are not legal-compliance findings and not\n"
        "  statements about care quality.\n"
        "- Prices are hospital-published standard charges. They are not\n"
        "  quotes and not a patient's out-of-pocket cost.\n"
    )


def _source_database_stats(path: Path, *, compute_hash: bool) -> dict[str, object]:
    stat = path.stat()
    return {
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        "sha256": _sha256_file(path) if compute_hash else None,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_relation(spec: EvidenceExportSpec) -> str:
    return ".".join([_quote_identifier(spec.source_schema), _quote_identifier(spec.source_table)])


def _sql_string_literal(path: Path) -> str:
    return str(path).replace("'", "''")


def _extract_markdown_sql_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    inside = False
    start_line = 0
    fence_lines: list[str] = []

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if inside:
                block = "\n".join(fence_lines)
                if _looks_like_sql(block):
                    blocks.append((start_line, _strip_sql_comments(block)))
                inside = False
                fence_lines = []
            else:
                info = stripped[3:].strip()
                if info and not info.lower().startswith(("bash", "text", "python", "yaml", "json")):
                    inside = True
                    start_line = index + 1
                    fence_lines = []
            continue
        if inside:
            fence_lines.append(line)

    return blocks


def _looks_like_sql(text: str) -> bool:
    return bool(re.search(r"\b(select|with|from|join)\b", text, re.I))


def _strip_sql_comments(text: str) -> str:
    stripped_lines = []
    for line in text.splitlines():
        stripped_lines.append(re.sub(r"--.*$", "", line))
    return "\n".join(stripped_lines)


def _line_for_offset(text: str, offset: int, block_start_line: int) -> tuple[int, str]:
    prefix = text[:offset]
    line_number = block_start_line + prefix.count("\n")
    line_start = prefix.rfind("\n") + 1
    line_end = text.find("\n", offset)
    if line_end == -1:
        line_end = len(text)
    return line_number, text[line_start:line_end]
