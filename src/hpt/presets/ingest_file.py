from pathlib import Path

from hpt.cli import ingest_logic


def ingest_file() -> None:
    bronze_root = Path(__file__).resolve().parents[3] / "data/bronze"
    quarantine_root = Path(__file__).resolve().parents[3] / "data/quarantine"
    ingest_logic(
        hospital_ids="vumc",
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
        log_level="INFO",
    )


if __name__ == "__main__":
    ingest_file()
