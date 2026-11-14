"""Stable Search REST contracts: bounded writes, hybrid retrieval and schema checks."""

import json
import time
from urllib.parse import quote

from core.auth import security_filter
from core.azure import ServiceError, endpoint, request, retry_delay


def schema(name: str, profile) -> dict:
    def field(name, kind="Edm.String", **options):
        return {"name": name, "type": kind, **options}

    fields = [
        field("id", key=True, filterable=True, sortable=True),
        field("document_id", filterable=True),
        field("tenant_id", filterable=True),
        field("generation", filterable=True),
        field("profile_id", filterable=True),
        field("source_etag"),
        field("visibility", filterable=True),
        field("allowed_groups", "Collection(Edm.String)", filterable=True),
        field("content", searchable=True),
        field("title", searchable=True),
        field("context", searchable=True),
        field("category", filterable=True),
        field("summary", searchable=True),
        field("keywords", "Collection(Edm.String)", searchable=True),
        field("sourcefile", filterable=True),
        field("sourcepages"),
        field("storageUrl"),
        field("pages", "Collection(Edm.Int32)"),
        field("start", "Edm.Int32"),
        field("end", "Edm.Int32"),
        field(
            "embedding",
            "Collection(Edm.Single)",
            searchable=True,
            retrievable=False,
            stored=False,
            dimensions=profile.embedding.dimensions,
            vectorSearchProfile="embedding-profile",
        ),
    ]
    vector_profile = {"name": "embedding-profile", "algorithm": "hnsw"}
    vector_search = {
        "algorithms": [{"name": "hnsw", "kind": "hnsw", "hnswParameters": {"metric": "cosine"}}],
        "profiles": [vector_profile],
    }
    if profile.index.compression != "none":
        vector_profile["compression"] = "compressed"
        vector_search["compressions"] = [
            {
                "name": "compressed",
                "kind": "scalarQuantization"
                if profile.index.compression == "scalar"
                else "binaryQuantization",
                "rescoringOptions": {
                    "enableRescoring": True,
                    "defaultOversampling": 4,
                    "rescoreStorageMethod": "preserveOriginals",
                },
            }
        ]
    return {
        "name": name,
        "description": f"indexadillo:{profile.fingerprint()}",
        "fields": fields,
        "vectorSearch": vector_search,
        "semantic": {
            "configurations": [
                {
                    "name": "default",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [{"fieldName": "content"}, {"fieldName": "context"}],
                        "prioritizedKeywordsFields": [{"fieldName": "keywords"}],
                    },
                }
            ]
        },
    }


class Search:
    def __init__(self, profile, identity="ingestion"):
        self.profile = profile
        self.identity = identity
        self.base = endpoint("SEARCH_SERVICE_ENDPOINT")

    def call(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        if method == "PUT":
            headers.setdefault("Prefer", "return=representation")
        return request(
            method,
            f"{self.base}/{path}",
            identity=self.identity,
            params={"api-version": self.profile.index.api_version},
            headers=headers,
            **kwargs,
        )

    def ensure_index(self, name):
        expected = schema(name, self.profile)
        response = self.call("GET", f"indexes/{name}", acceptable=(200, 404))
        if response.status_code == 404:
            created = self.call(
                "PUT",
                f"indexes/{name}",
                json=expected,
                headers={"If-None-Match": "*"},
                acceptable=(200, 201, 409, 412),
            )
            if created.status_code in (200, 201):
                return
            response = self.call("GET", f"indexes/{name}")
        existing = response.json()
        if existing.get("description") != expected["description"]:
            raise ValueError("Index profile mismatch: build a new versioned index")
        actual_fields = {item["name"]: item for item in existing["fields"]}
        for item in expected["fields"]:
            actual = actual_fields.get(item["name"], {})
            if any(actual.get(key) != value for key, value in item.items()):
                raise ValueError("Index schema mismatch: build a new versioned index")

    def write(self, name, documents, guard=None):
        for batch in write_batches(documents):
            pending = batch
            for attempt in range(5):
                if guard:
                    guard.check()
                result = self.call(
                    "POST",
                    f"indexes/{name}/docs/index",
                    json={"value": pending},
                    acceptable=(200, 207),
                    lease_guard=guard,
                ).json()["value"]
                outcomes = {item["key"]: item for item in result}
                if set(outcomes) != {doc["id"] for doc in pending}:
                    raise ValueError("Search returned an incomplete indexing result")
                failed = []
                for doc in pending:
                    outcome = outcomes[doc["id"]]
                    if outcome["status"]:
                        continue
                    code = outcome.get("statusCode", 500)
                    if code not in (408, 409, 422, 429, 500, 502, 503, 504):
                        raise ServiceError(code, "indexing")
                    failed.append(doc)
                if not failed:
                    break
                if attempt == 4:
                    raise ServiceError(503, "indexing")
                pending = failed
                time.sleep(retry_delay(attempt))

    def delete(self, name, ids, guard=None):
        self.write(name, [{"@search.action": "delete", "id": key} for key in ids], guard)

    def keys(self, name, document_id, guard=None):
        """Recover keys even if a lost lease left an upload outside the manifest."""
        after = ""
        for _ in range(100):
            body = {
                "search": "*",
                "select": "id",
                "top": 1000,
                "orderby": "id asc",
                "filter": f"document_id eq '{document_id}'" + (f" and id gt '{after}'" if after else ""),
            }
            page = self.call("POST", f"indexes/{name}/docs/search", json=body, lease_guard=guard).json()[
                "value"
            ]
            for item in page:
                yield item["id"]
            if len(page) < 1000:
                return
            after = page[-1]["id"]
        raise ValueError("Document key recovery exceeded its bounded page limit")

    def query(self, name, query, principal, *, vector=None, mode="hybrid", semantic=True, top=10):
        body = {
            "search": query if mode != "vector" else None,
            "filter": security_filter(principal),
            "top": top,
            "select": "id,document_id,content,context,title,sourcefile,sourcepages,pages,start,end,generation,source_etag",
        }
        if mode != "keyword":
            if not vector or len(vector) != self.profile.embedding.dimensions:
                raise ValueError("Query vector does not match the index profile")
            body["vectorQueries"] = [{"kind": "vector", "vector": vector, "fields": "embedding", "k": 50}]
            body["vectorFilterMode"] = "preFilter"
        if semantic:
            body.update(queryType="semantic", semanticConfiguration="default", semanticQuery=query)
        return self.call("POST", f"indexes/{name}/docs/search", json=body).json()["value"]

    def document(self, name, document_id, principal):
        body = {
            "search": "*",
            "filter": f"{security_filter(principal)} and document_id eq '{document_id}'",
            "top": 1,
            "select": "document_id,sourcefile,source_etag",
        }
        values = self.call("POST", f"indexes/{name}/docs/search", json=body).json()["value"]
        return values[0] if values else None

    def alias(self, alias, index):
        self.ensure_index(index)
        return self.call("PUT", f"aliases/{alias}", json={"name": alias, "indexes": [index]}).json()

    def knowledge_source(self, name, index):
        # targetIndexName requires a physical index; aliases are not supported.
        self.ensure_index(index)
        return self.call(
            "PUT",
            f"knowledgesources/{quote(name, safe='')}",
            json={
                "name": name,
                "kind": "searchIndex",
                "searchIndexParameters": {
                    "searchIndexName": index,
                    "sourceDataFields": [{"name": "content"}, {"name": "sourcefile"}],
                    "searchFields": [{"name": "content"}, {"name": "title"}, {"name": "context"}],
                    "semanticConfigurationName": "default",
                },
            },
        ).json()


def write_batches(documents, max_bytes=14_000_000, max_items=1000):
    batch, count = [], len(b'{"value":[]}')
    for document in documents:
        size = len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()) + 1
        if size + len(b'{"value":[]}') > max_bytes:
            raise ValueError("A search document exceeds the upload byte limit")
        if batch and (len(batch) >= max_items or count + size > max_bytes):
            yield batch
            batch, count = [], len(b'{"value":[]}')
        batch.append(document)
        count += size
    if batch:
        yield batch
