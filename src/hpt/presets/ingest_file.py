from pathlib import Path

from hpt.cli import ingest_logic
from hpt.ingest.config import IngestConfig


def ingest_file() -> None:
    bronze_root = Path(__file__).resolve().parents[3] / "data/bronze"
    quarantine_root = Path(__file__).resolve().parents[3] / "data/quarantine"
    registry_path = Path(__file__).resolve().parents[3] / "data/registry.json"
    ingest_logic(
        hospital_id="vumc",
        ingest_all=True,
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
        registry_path=registry_path,
        log_level="INFO",
    )


if __name__ == "__main__":
    ingest_file()
