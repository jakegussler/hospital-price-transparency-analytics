import httpx

from hpt.ingest.config import ClientConfig


def build_httpx_client(cfg: ClientConfig) -> httpx.Client:
    transport = httpx.HTTPTransport(retries=cfg.retries)
    return httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(
            connect=cfg.connect_timeout_s,
            read=cfg.read_timeout_s,
            timeout=cfg.timeout_s,
        ),
        headers={"User-Agent": cfg.user_agent},
        follow_redirects=True,
    )
