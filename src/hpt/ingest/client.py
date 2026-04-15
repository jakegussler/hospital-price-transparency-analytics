import httpx
from hpt.ingest.config import IngestConfig

def build_httpx_client(cfg: IngestConfig) -> httpx.Client:
    transport = httpx.HTTPTransport(retries=cfg.http_retries)
    return httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(connect=cfg.http_connect_timeout, read=cfg.http_read_timeout, timeout=cfg.http_timeout),
        headers={"User-Agent": cfg.user_agent},
        follow_redirects=True,
    )
