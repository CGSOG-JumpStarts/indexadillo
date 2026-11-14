"""Managed-identity artifact storage and renewable document/service leases."""

import atexit
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from urllib.parse import quote

from azure.core import MatchConditions
from azure.core.exceptions import AzureError, HttpResponseError, ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings

from core.azure import credential
from core.config import required


class Superseded(RuntimeError):
    """The immutable source version is no longer current."""


class Busy(RuntimeError):
    """A renewable resource lease is in use; retry through Durable Functions."""


def digest(value) -> str:
    data = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def document_id(tenant: str, account: str, container: str, name: str) -> str:
    return digest([tenant, account, container, name])


@lru_cache
def blobs(account: str, identity="ingestion"):
    result = BlobServiceClient(f"https://{account}.blob.core.windows.net", credential=credential(identity))
    atexit.register(result.close)
    return result


class LeaseGuard:
    def __init__(self, lease):
        self.lease = lease
        self.stopped = threading.Event()
        self.lost = threading.Event()
        self.last_renewed = time.monotonic()

    def renew(self):
        while not self.stopped.wait(20):
            try:
                self.lease.renew()
                self.last_renewed = time.monotonic()
            except AzureError:
                self.lost.set()
                return

    def check(self):
        if self.lost.is_set() or time.monotonic() - self.last_renewed >= 45:
            raise Busy("Lease renewal failed")


class Store:
    def __init__(self, identity="ingestion"):
        self.identity = identity
        self.account = required("ARTIFACT_STORAGE_ACCOUNT_NAME")
        self.service = blobs(self.account, identity)

    def read(self, container: str, name: str):
        try:
            return json.loads(self.service.get_blob_client(container, name).download_blob().readall())
        except ResourceNotFoundError:
            return None

    def write(self, container: str, name: str, value, *, immutable=False):
        try:
            self.service.get_blob_client(container, name).upload_blob(
                json.dumps(value, ensure_ascii=False).encode(),
                overwrite=not immutable,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except ResourceExistsError:
            if not immutable:
                raise

    def artifact(self, name: str, value):
        self.write("artifacts", name, value, immutable=True)
        return name

    @contextmanager
    def lock(self, name: str):
        blob = self.service.get_blob_client("locks", name)
        try:
            blob.upload_blob(b"", overwrite=False)
        except ResourceExistsError:
            pass
        try:
            lease = blob.acquire_lease(lease_duration=60)
        except HttpResponseError as exc:
            if exc.status_code == 409:
                raise Busy("Resource currently leased") from exc
            raise
        guard = LeaseGuard(lease)
        thread = threading.Thread(target=guard.renew, daemon=True)
        thread.start()
        try:
            yield guard
            guard.check()
        finally:
            guard.stopped.set()
            thread.join(timeout=2)
            try:
                lease.release()
            except AzureError:
                pass

    @contextmanager
    def service_slot(self, service: str):
        slots = int(os.getenv(f"{service.upper()}_CONCURRENCY", "4"))
        if not 1 <= slots <= 64:
            raise ValueError("Service concurrency must be between 1 and 64")
        for slot in range(slots):
            manager = self.lock(f"services/{service}/{slot}")
            try:
                guard = manager.__enter__()
            except Busy:
                continue
            try:
                yield guard
            except BaseException as exc:
                manager.__exit__(type(exc), exc, exc.__traceback__)
                raise
            else:
                manager.__exit__(None, None, None)
            return
        raise Busy("All downstream service slots are occupied")

    def manifest_name(self, ref) -> str:
        return f"{ref['tenant_id']}/{ref['index_name']}/{ref['document_id']}.json"

    def source(self, ref):
        return blobs(required("SOURCE_STORAGE_ACCOUNT_NAME"), self.identity).get_blob_client(
            os.getenv("BLOB_CONTAINER_NAME", "source"), ref["source_name"]
        )

    def current(self, ref):
        try:
            return self.source(ref).get_blob_properties()
        except ResourceNotFoundError:
            return None

    def assert_current(self, ref):
        props = self.current(ref)
        if props is None or str(props.etag) != ref["etag"]:
            raise Superseded("Source has changed")
        return props

    def source_bytes(self, ref, max_bytes: int) -> bytes:
        props = self.assert_current(ref)
        if props.size > max_bytes:
            raise ValueError("Source exceeds configured byte limit")
        try:
            return (
                self.source(ref)
                .download_blob(
                    etag=ref["etag"], match_condition=MatchConditions.IfNotModified, max_concurrency=1
                )
                .readall()
            )
        except HttpResponseError as exc:
            if exc.status_code in (404, 412):
                raise Superseded("Source has changed") from exc
            raise

    def source_url(self, ref):
        account = required("SOURCE_STORAGE_ACCOUNT_NAME")
        container = os.getenv("BLOB_CONTAINER_NAME", "source")
        return f"https://{account}.blob.core.windows.net/{container}/{quote(ref['source_name'], safe='/')}"


@lru_cache
def store(identity="ingestion") -> Store:
    return Store(identity)
