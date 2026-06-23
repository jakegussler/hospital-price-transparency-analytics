"""Re-vendor the CMS MRF reference fixtures used by the sniffer tests.

Why this exists
---------------
``tests/ingest/test_mrf_sniffer.py`` validates the schema sniffer against real
CMS example/template files. Those files live upstream in
``github.com/CMSgov/hospital-price-transparency``, which is cloned into
``docs/cms_reference/`` for human/agent reference but is git-ignored, so CI never
sees it. To keep the tests self-contained and reproducible we commit a small,
pinned copy of the six files we need under ``tests/fixtures/cms_reference/``.

This script regenerates those committed fixtures from a pinned upstream commit:
it clones the CMS repo into a temp dir, checks out ``CMS_COMMIT``, and copies the
mapped files into place. Run it when bumping to a newer CMS spec snapshot; then
review the diff and update ``CMS_COMMIT`` here (and the provenance comment in the
test) before committing.

Usage
-----
    python scripts/vendor_cms_fixtures.py
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "cms_reference"

CMS_REPO_URL = "https://github.com/CMSgov/hospital-price-transparency.git"
# Pinned upstream commit the committed fixtures are sourced from. Bump
# deliberately, re-run this script, and review the resulting diff.
CMS_COMMIT = "7c8bdce"

# Mapping of upstream path (relative to the CMS repo root) -> committed fixture
# filename (relative to FIXTURE_ROOT). Names are flattened for readability; the
# test references the flattened names.
FIXTURES: dict[str, str] = {
    "examples/JSON/v3_json_format_example.json": "v3_json_format_example.json",
    "archive/examples/JSON/V2.0.0_JSON_Format_Example.json": "V2.0.0_JSON_Format_Example.json",
    "archive/documentation/CSV/templates/V2.0.0_Tall_CSV_Format_Template.csv": (
        "V2.0.0_Tall_CSV_Format_Template.csv"
    ),
    "archive/documentation/CSV/templates/V2.0.0_Wide_CSV_Format_Template.csv": (
        "V2.0.0_Wide_CSV_Format_Template.csv"
    ),
    "examples/CSV/Tall Format Examples/V3.0.0_Tall_CSV_Format_Example.csv": (
        "V3.0.0_Tall_CSV_Format_Example.csv"
    ),
    "documentation/CSV/templates/V3.0.0_Wide_CSV_Format_Template.csv": (
        "V3.0.0_Wide_CSV_Format_Template.csv"
    ),
}


def _clone_pinned(dest: Path) -> None:
    """Clone the CMS repo into ``dest`` and check out the pinned commit."""
    subprocess.run(["git", "clone", "--quiet", CMS_REPO_URL, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", CMS_COMMIT], check=True)


def main() -> None:
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        clone_dir = Path(tmp) / "hospital-price-transparency"
        print(f"Cloning {CMS_REPO_URL} @ {CMS_COMMIT} ...")
        _clone_pinned(clone_dir)

        for src_rel, dest_name in FIXTURES.items():
            src = clone_dir / src_rel
            if not src.is_file():
                raise FileNotFoundError(
                    f"upstream file missing at {CMS_COMMIT}: {src_rel} "
                    "(did the CMS repo layout change?)"
                )
            dest = FIXTURE_ROOT / dest_name
            shutil.copyfile(src, dest)
            print(f"  {src_rel} -> {dest.relative_to(PROJECT_ROOT)}")

    print(f"\nVendored {len(FIXTURES)} fixtures into {FIXTURE_ROOT.relative_to(PROJECT_ROOT)}.")
    print("Review `git diff`/`git status` and commit if the changes are expected.")


if __name__ == "__main__":
    main()
