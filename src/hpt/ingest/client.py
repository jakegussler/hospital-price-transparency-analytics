import logging

import httpx

from hpt.ingest.config import ClientConfig

logger = logging.getLogger(__name__)


def build_httpx_client(cfg: ClientConfig) -> httpx.Client:
    logger.debug(
        "http_client_config",
        extra={
            "connect_timeout_s": cfg.connect_timeout_s,
            "read_timeout_s": cfg.read_timeout_s,
            "timeout_s": cfg.timeout_s,
            "retries": cfg.retries,
            "user_agent": cfg.user_agent,
        },
    )
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
