from unittest.mock import Mock

import httpx
import pytest

from core.auth import Principal
from core.azure import ServiceError
from core.config import ProcessingProfile, TenantScope
from core.search import Search, schema, write_batches


def result(items, code=200):
    return httpx.Response(code, json={"value": items})


def test_partial_batch_retries_only_failed_documents(monkeypatch):
    search = Search(ProcessingProfile())
    search.call = Mock(
        side_effect=[
            result([{"key": "a", "status": True}, {"key": "b", "status": False, "statusCode": 503}]),
            result([{"key": "b", "status": True}]),
        ]
    )
    monkeypatch.setattr("core.search.time.sleep", lambda _: None)
    docs = [{"id": "a"}, {"id": "b"}]
    search.write("index", docs)
    assert search.call.call_args_list[1].kwargs["json"]["value"] == [docs[1]]


def test_permanent_indexing_error_fails_without_retry():
    search = Search(ProcessingProfile())
    search.call = Mock(return_value=result([{"key": "a", "status": False, "statusCode": 400}]))
    with pytest.raises(ServiceError):
        search.write("index", [{"id": "a"}])
    assert search.call.call_count == 1


def test_missing_indexing_outcome_is_failure():
    search = Search(ProcessingProfile())
    search.call = Mock(return_value=result([]))
    with pytest.raises(ValueError):
        search.write("index", [{"id": "a"}])


def test_batches_obey_utf8_byte_and_item_limits():
    docs = [{"id": str(i), "content": "😀" * 10} for i in range(7)]
    batches = list(write_batches(docs, max_bytes=170, max_items=3))
    assert sum(len(batch) for batch in batches) == 7
    import json

    assert all(
        len(json.dumps({"value": batch}, ensure_ascii=False, separators=(",", ":")).encode()) <= 170
        for batch in batches
    )
    with pytest.raises(ValueError):
        list(write_batches(docs, max_bytes=30))


def test_hybrid_query_always_pre_filters_permissions_and_excludes_vectors():
    profile = ProcessingProfile()
    principal = Principal(
        "caller",
        TenantScope(tenant_id="tenant-a", prefix="a/", indexes=["index"]),
        frozenset({"Reader"}),
        ("group-a",),
    )
    search = Search(profile, identity="query")
    search.call = Mock(return_value=result([]))
    search.query("index", "contract", principal, vector=[0.0] * 3072)
    body = search.call.call_args.kwargs["json"]
    assert body["vectorQueries"][0]["k"] == 50
    assert body["vectorFilterMode"] == "preFilter"
    assert "tenant_id eq 'tenant-a'" in body["filter"]
    assert "group-a" in body["filter"]
    assert "embedding" not in body["select"]
    assert body["queryType"] == "semantic"


def test_schema_compresses_and_does_not_return_vectors():
    definition = schema("index", ProcessingProfile())
    vector = next(f for f in definition["fields"] if f["name"] == "embedding")
    assert vector["dimensions"] == 3072 and not vector["retrievable"]
    assert definition["vectorSearch"]["compressions"][0]["kind"] == "scalarQuantization"


def test_existing_incompatible_index_is_not_mutated():
    search = Search(ProcessingProfile())
    search.call = Mock(return_value=httpx.Response(200, json={"description": "legacy", "fields": []}))
    with pytest.raises(ValueError, match="profile mismatch"):
        search.ensure_index("index")
    assert search.call.call_count == 1


def test_key_recovery_paginates_without_skipping_or_duplicating_keys():
    search = Search(ProcessingProfile())
    first = [{"id": f"document-{i:05}"} for i in range(1000)]
    last = [{"id": f"document-{i:05}"} for i in range(1000, 1003)]
    search.call = Mock(side_effect=[result(first), result(last)])
    assert list(search.keys("index", "document")) == [item["id"] for item in first + last]
    body = search.call.call_args_list[1].kwargs["json"]
    assert body["filter"] == "document_id eq 'document' and id gt 'document-00999'"
    assert body["orderby"] == "id asc"


def test_index_creation_requests_representation_and_records_the_profile():
    search = Search(ProcessingProfile())
    search.call = Mock(side_effect=[httpx.Response(404), httpx.Response(201, json={})])
    search.ensure_index("index")
    created = search.call.call_args_list[1]
    assert created.kwargs["headers"]["If-None-Match"] == "*"
    assert created.kwargs["json"]["description"].startswith("indexadillo:")
