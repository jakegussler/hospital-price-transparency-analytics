from __future__ import annotations

from pathlib import Path

from hpt.presentation.evidence_export import scan_evidence_sql


def test_scan_evidence_sql_allows_public_hpt_sources_and_prose(tmp_path: Path) -> None:
    app = tmp_path / "evidence"
    (app / "sources" / "hpt").mkdir(parents=True)
    (app / "src" / "pages").mkdir(parents=True)
    (app / "sources" / "hpt" / "hospital_overview.sql").write_text(
        "select * from read_parquet('sources/hpt/data/hospital_overview.parquet')",
        encoding="utf-8",
    )
    (app / "src" / "pages" / "methodology.md").write_text(
        "This prose can mention main_gold, Bronze, raw files, and quarantine.",
        encoding="utf-8",
    )

    assert scan_evidence_sql(app) == []


def test_scan_evidence_sql_flags_disallowed_executable_references(tmp_path: Path) -> None:
    app = tmp_path / "evidence"
    (app / "src" / "pages").mkdir(parents=True)
    (app / "src" / "pages" / "bad.md").write_text(
        """
# Bad

```sql bad_query
select *
from main_gold.gld_fct__rate_observations
```
""",
        encoding="utf-8",
    )

    violations = scan_evidence_sql(app)

    assert {(violation.token, violation.line_number) for violation in violations} == {
        ("main_gold", 6),
        ("gld_fct__", 6),
    }


def test_checked_in_evidence_app_uses_only_public_sql_sources() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    violations = scan_evidence_sql(repo_root / "apps" / "evidence")

    assert violations == []
