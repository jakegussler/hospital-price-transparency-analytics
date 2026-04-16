from hpt.ingest.download import download_hospital
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.registry.models import HospitalSource
from hpt.registry.loader import get_hospital
from hpt.ingest.config import IngestConfig
from hpt.ingest.client import build_httpx_client
from pathlib import Path
import os
from dotenv import load_dotenv



def download_hospitals(hospitals: list[HospitalSource]):
    cfg = IngestConfig.from_env()
    storage = BronzeStorage(cfg.bronze_base_uri)
    snapshots = SnapshotManager(storage)
    client = build_httpx_client(cfg)
    for hospital in hospitals:
        download_hospital(hospital, storage, snapshots, client)

if __name__ == "__main__":
    download_hospitals([get_hospital("erlanger-baroness")])