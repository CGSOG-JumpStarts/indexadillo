"""Reusable, bounded Azure clients with sanitized failures and transient retries."""

import atexit
import logging
import os
import random
import time
from email.utils import parsedate_to_datetime
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from core.config import required

log = logging.getLogger("indexadillo")


class ServiceError(RuntimeError):
    def __init__(self, status: int, service: str = "azure"):
        self.status = status
        super().__init__(f"{service} request failed ({status})")


@lru_cache
def credential(kind: str = "ingestion"):
    client_id = os.getenv("QUERY_CLIENT_ID" if kind == "query" else "AZURE_CLIENT_ID")
    if os.getenv("WEBSITE_INSTANCE_ID"):
        result = ManagedIdentityCredential(client_id=client_id)
    else:
        result = DefaultAzureCredential(managed_identity_client_id=client_id)
    atexit.register(result.close)
    return result


@lru_cache
def transport() -> httpx.Client:
    result = httpx.Client(
        timeout=httpx.Timeout(60, connect=10),
        limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        follow_redirects=False,
    )
    atexit.register(result.close)
    return result


def endpoint(name: str) -> str:
    value = required(name).rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.query or parsed.username or parsed.fragment:
        raise ValueError(f"{name} must be an HTTPS service endpoint")
    return value


def retry_delay(attempt: int, headers=None) -> float:
    value = (headers or {}).get("Retry-After")
    if value:
        try:
            return min(120, max(0, float(value)))
        except ValueError:
            try:
                return min(120, max(0, parsedate_to_datetime(value).timestamp() - time.time()))
            except (ValueError, TypeError):
                pass
    return min(30, 2**attempt) + random.uniform(0, 0.5)  # noqa: S311


def request(
    method: str,
    url: str,
    *,
    scope="https://search.azure.com/.default",
    identity="ingestion",
    acceptable=(200, 201, 202, 204),
    retry_safe=True,
    lease_guard=None,
    **kwargs,
) -> httpx.Response:
    attempts = 5 if retry_safe else 1
    original_headers = kwargs.pop("headers", {})
    for attempt in range(attempts):
        if lease_guard:
            lease_guard.check()
        headers = dict(original_headers)
        headers["Authorization"] = f"Bearer {credential(identity).get_token(scope).token}"
        try:
            response = transport().request(method, url, headers=headers, **kwargs)
        except httpx.TransportError as exc:
            if attempt == attempts - 1:
                raise ServiceError(503) from exc
            time.sleep(retry_delay(attempt))
            continue
        if response.status_code in acceptable:
            return response
        if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt == attempts - 1:
            raise ServiceError(response.status_code)
        log.warning("downstream_retry status=%s attempt=%s", response.status_code, attempt + 1)
        time.sleep(retry_delay(attempt, response.headers))
    raise AssertionError("unreachable")
