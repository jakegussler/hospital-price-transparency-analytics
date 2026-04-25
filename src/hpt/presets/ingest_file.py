from hpt.cli import ingest_logic
from hpt.utils.paths import get_default_data_root


def ingest_file() -> None:
    data_root = get_default_data_root()
    bronze_root = data_root / "bronze"
    quarantine_root = data_root / "quarantine"
    ingest_logic(
        hospital_ids="ballad-jcmc",
        raw_base_uri=data_root,
        bronze_root=bronze_root,
        quarantine_root=quarantine_root,
        log_level="INFO",
    )


if __name__ == "__main__":
    ingest_file()
