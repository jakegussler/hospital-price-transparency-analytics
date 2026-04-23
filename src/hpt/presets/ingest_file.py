from pathlib import Path

from hpt.cli import ingest_logic
from hpt.ingest.config import IngestConfig


def ingest_file() -> None:
    bronze_root = Path(__file__).resolve().parents[3] / "data/bronze"
    quarantine_root = Path(__file__).resolve().parents[3] / "data/quarantine"
    config = IngestConfig.from_env(
        hospital_id="vumc",
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
    )
    ingest_logic(config)


if __name__ == "__main__":
    ingest_file()
