"""Debugger-friendly preset for downloading every configured hospital MRF."""

from hpt.cli import download_logic
from hpt.utils.paths import get_default_data_root


def download_all_preset() -> None:
    data_root = get_default_data_root()
    download_logic(
        hospital_ids=None,
        raw_base_uri=data_root,
        dry_run=False,
        force=False,
        registry_path=None,
        log_level="DEBUG",
    )


if __name__ == "__main__":
    download_all_preset()
