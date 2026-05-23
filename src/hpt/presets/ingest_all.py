"""Debugger-friendly preset for ingesting every current hospital snapshot."""

from hpt.cli import ingest_logic
from hpt.utils.paths import get_default_data_root


def ingest_all_preset() -> None:
    data_root = get_default_data_root()
    ingest_logic(
        hospital_ids=None,
        raw_base_uri=data_root,
        bronze_root=data_root / "bronze",
        quarantine_root=data_root / "quarantine",
        registry_path=None,
        log_level="DEBUG",
    )


if __name__ == "__main__":
    ingest_all_preset()
