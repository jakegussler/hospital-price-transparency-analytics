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
    require_nonzero: bool = False

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
        require_nonzero=True,
    ),
    EvidenceExportSpec(
        public_name="service_market_explorer",
        source_schema="main_gold",
        source_table="gld_bi__service_market_explorer",
        require_nonzero=True,
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
        require_nonzero=True,
    ),
)

PUBLIC_METADATA_NAME = "public_metadata.parquet"
DEFAULT_CORPUS_LABEL = "Nashville metro"

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


def export_evidence_artifact(
    *,
    source_duckdb: Path,
    target_dir: Path,
    replace: bool = False,
    corpus_label: str = DEFAULT_CORPUS_LABEL,
    exported_at: datetime | None = None,
    compute_source_hash: bool = True,
) -> dict[str, int]:
    """Export allowlisted Gold BI marts to Parquet files for Evidence.

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

    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_dir = parent / f".{target_dir.name}.tmp-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)

    try:
        source_stats = _source_database_stats(
            source_duckdb, compute_hash=compute_source_hash
        )
        with duckdb.connect(str(source_duckdb), read_only=True) as con:
            row_counts = _export_allowlisted_tables(con, temp_dir)
            _write_public_metadata(
                con=con,
                temp_dir=temp_dir,
                row_counts=row_counts,
                corpus_label=corpus_label,
                exported_at=exported_at,
                source_stats=source_stats,
            )

        if target_dir.exists():
            if replace:
                shutil.rmtree(target_dir)
            else:
                target_dir.rmdir()
        temp_dir.replace(target_dir)
        return row_counts
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
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


def _export_allowlisted_tables(con: object, temp_dir: Path) -> dict[str, int]:
    row_counts: dict[str, int] = {}

    for spec in EVIDENCE_EXPORTS:
        _assert_relation_exists(con, spec)
        row_count = int(
            con.execute(f"select count(*) from {_quote_relation(spec)}").fetchone()[0]
        )
        if spec.require_nonzero and row_count == 0:
            raise EvidenceExportError(
                f"Required BI mart {spec.source_relation} has zero rows."
            )
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
) -> None:
    metadata_rows = [
        (
            exported_at.isoformat(),
            corpus_label,
            spec.public_name,
            spec.source_schema,
            spec.source_table,
            row_counts[spec.public_name],
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
            public_table_name varchar,
            source_schema varchar,
            source_table varchar,
            row_count bigint,
            source_database_size_bytes bigint,
            source_database_mtime_utc varchar,
            source_database_sha256 varchar
        )
        """
    )
    con.executemany(
        """
        insert into evidence_public_metadata values (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return ".".join(
        [_quote_identifier(spec.source_schema), _quote_identifier(spec.source_table)]
    )


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
