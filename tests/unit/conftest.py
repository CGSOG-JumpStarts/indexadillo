import copy
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from core.config import ProcessingProfile, profile, scopes
from core.storage import Superseded, document_id


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("SOURCE_STORAGE_ACCOUNT_NAME", "sourceaccount")
    monkeypatch.setenv("ARTIFACT_STORAGE_ACCOUNT_NAME", "artifactaccount")
    monkeypatch.setenv("SEARCH_SERVICE_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://models.example.test")
    monkeypatch.setenv("ENTRA_TENANT_ID", "tenant-a")
    monkeypatch.setenv("ENTRA_AUDIENCE", "api-client")
    monkeypatch.setenv(
        "TENANT_SCOPES_JSON",
        json.dumps(
            {
                "tenant-a": {"tenant_id": "tenant-a", "prefix": "tenants/a/", "indexes": ["documents-v2"]},
            }
        ),
    )
    monkeypatch.delenv("AUTH_MODE", raising=False)
    profile.cache_clear()
    scopes.cache_clear()
    yield
    profile.cache_clear()
    scopes.cache_clear()


@pytest.fixture
def ref():
    return {
        "tenant_id": "tenant-a",
        "source_name": "tenants/a/reports/report.pdf",
        "document_id": document_id("tenant-a", "sourceaccount", "source", "tenants/a/reports/report.pdf"),
        "etag": "v1",
        "index_name": "documents-v2",
        "profile": ProcessingProfile().model_dump(),
        "allowed_groups": [],
        "visibility": "tenant",
        "artifact": "tenant-a/embeddings/test.json",
    }


class Guard:
    def check(self):
        pass


class MemoryStore:
    def __init__(self, ref):
        self.data = {}
        self.sources = {ref["source_name"]: ref["etag"]}
        self.locks = set()
        self.contents = {ref["source_name"]: b"# Report\n\nEvidence from the source document."}
        self.write("artifacts", ref["artifact"], {"chunks": [self.chunk(0), self.chunk(1)]})

    @staticmethod
    def chunk(position):
        return {
            "text": f"chunk {position}",
            "embedding": [0.0] * 3072,
            "start": position * 10,
            "end": position * 10 + 7,
            "pages": [position + 1],
        }

    def read(self, container, name):
        return copy.deepcopy(self.data.get((container, name)))

    def write(self, container, name, value, **kwargs):
        self.data[(container, name)] = copy.deepcopy(value)

    def manifest_name(self, ref):
        return f"{ref['tenant_id']}/{ref['index_name']}/{ref['document_id']}.json"

    def current(self, ref):
        etag = self.sources.get(ref["source_name"])
        return (
            SimpleNamespace(
                etag=etag,
                size=len(self.contents.get(ref["source_name"], b"")),
                content_settings=SimpleNamespace(content_type="text/plain"),
            )
            if etag
            else None
        )

    def source_bytes(self, ref, max_bytes):
        self.assert_current(ref)
        data = self.contents[ref["source_name"]]
        assert len(data) <= max_bytes
        return data

    def artifact(self, name, value):
        self.write("artifacts", name, value)
        return name

    @contextmanager
    def service_slot(self, name):
        yield Guard()

    def assert_current(self, ref):
        value = self.current(ref)
        if not value or value.etag != ref["etag"]:
            raise Superseded()
        return value

    def source_url(self, ref):
        return "https://sourceaccount.blob.core.windows.net/source/" + ref["source_name"]

    @contextmanager
    def lock(self, name):
        assert name not in self.locks
        self.locks.add(name)
        try:
            yield Guard()
        finally:
            self.locks.remove(name)


class MemorySearch:
    def __init__(self):
        self.documents = {}
        self.interrupt_after = None
        self.after_write = None

    def write(self, index, documents, guard=None):
        for count, doc in enumerate(documents, 1):
            self.documents[doc["id"]] = copy.deepcopy(doc)
            if self.interrupt_after == count:
                raise TimeoutError("simulated partial upload")
        if self.after_write:
            self.after_write()

    def delete(self, index, ids, guard=None):
        for key in ids:
            self.documents.pop(key, None)

    def keys(self, index, document_id, guard=None):
        return [key for key, doc in self.documents.items() if doc.get("document_id") == document_id]


@pytest.fixture
def storage(ref):
    return MemoryStore(ref)


@pytest.fixture
def search():
    return MemorySearch()
