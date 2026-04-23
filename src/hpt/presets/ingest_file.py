from hpt.cli import ingest_logic
from pathlib import Path

def ingest_file() -> None:

    bronze_root = Path(__file__).resolve().parents[3] / "data/bronze"
    quarantine_root = Path(__file__).resolve().parents[3] / "data/quarantine"
    ingest_logic(
        hospital_id="vumc",
        ingest_all=False,
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
    )

if __name__ == "__main__":
    ingest_file()