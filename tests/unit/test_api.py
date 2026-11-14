import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import azure.functions as func
import pytest

import function_app as api
from core.auth import Principal
from core.config import scopes


def function(builder):
    return inspect.unwrap(builder._function.get_user_function())


def req(method="GET", route="index", body=None, params=None, route_params=None):
    return func.HttpRequest(
        method,
        f"https://api.example.test/api/{route}",
        params=params or {},
        route_params=route_params or {},
        body=json.dumps(body or {}).encode(),
    )


@pytest.fixture
def caller(monkeypatch):
    principal = Principal("caller", scopes()["tenant-a"], frozenset({"Reader", "Indexer"}), ())
    monkeypatch.setattr(api, "authorize", Mock(return_value=principal))
    return principal


async def test_anonymous_index_call_cannot_start_work():
    client = SimpleNamespace(start_new=AsyncMock())
    result = await function(api.index_http)(req("POST"), client)
    assert result.status_code == 401
    client.start_new.assert_not_called()


async def test_index_uses_configured_scope_and_returns_accepted_job(caller):
    client = SimpleNamespace(start_new=AsyncMock(return_value="job-123"))
    result = await function(api.index_http)(req("POST", body={"prefix_list": [""]}), client)
    assert result.status_code == 202
    assert result.headers["Location"] == "/api/status/job-123"
    job = client.start_new.call_args.kwargs["client_input"]
    assert job["prefix_list"] == ["tenants/a/"]
    assert job["scope"]["tenant_id"] == "tenant-a"


async def test_index_rejects_cross_tenant_index(caller):
    client = SimpleNamespace(start_new=AsyncMock())
    result = await function(api.index_http)(req("POST", body={"index_name": "other-tenant"}), client)
    assert result.status_code == 403
    client.start_new.assert_not_called()


async def test_search_requests_real_vector_with_query_identity(caller, monkeypatch):
    embedding = Mock(return_value=[[0.0] * 3072])
    query = Mock(
        return_value=[
            {
                "id": "chunk",
                "document_id": "document",
                "content": "found",
                "sourcefile": "tenants/a/report.pdf",
                "source_etag": "v1",
            }
        ]
    )
    monkeypatch.setattr(api, "embed", embedding)
    factory = Mock(return_value=SimpleNamespace(query=query))
    monkeypatch.setattr(api, "Search", factory)
    monkeypatch.setattr(
        api, "store", lambda _: SimpleNamespace(current=lambda _: SimpleNamespace(etag="v1", metadata={}))
    )
    result = await function(api.search_index)(req(params={"q": "contract"}))
    assert result.status_code == 200
    assert embedding.call_args.kwargs["identity"] == "query"
    assert factory.call_args.kwargs["identity"] == "query"
    assert query.call_args.kwargs["vector"] == [0.0] * 3072


async def test_search_rechecks_revoked_source_permissions_before_returning_text(caller, monkeypatch):
    query = Mock(
        return_value=[
            {
                "id": "chunk",
                "document_id": "document",
                "content": "private text",
                "sourcefile": "tenants/a/report.pdf",
                "source_etag": "old",
            }
        ]
    )
    monkeypatch.setattr(api, "Search", Mock(return_value=SimpleNamespace(query=query)))
    monkeypatch.setattr(
        api,
        "store",
        lambda _: SimpleNamespace(
            current=lambda _: SimpleNamespace(etag="new", metadata={"visibility": "restricted"})
        ),
    )
    result = await function(api.search_index)(req(params={"q": "contract", "mode": "keyword"}))
    assert result.status_code == 200
    assert json.loads(result.get_body()) == []


async def test_citation_download_checks_search_and_current_source_permissions(caller, monkeypatch):
    document = Mock(
        return_value={"document_id": "a" * 64, "sourcefile": "tenants/a/report.pdf", "source_etag": "v1"}
    )
    monkeypatch.setattr(api, "Search", Mock(return_value=SimpleNamespace(document=document)))
    source_bytes = Mock(return_value=b"source bytes")
    monkeypatch.setattr(
        api,
        "store",
        lambda _: SimpleNamespace(
            current=lambda _: SimpleNamespace(etag="v1", metadata={}), source_bytes=source_bytes
        ),
    )
    result = await function(api.download_document)(req(route_params={"id": "a" * 64}))
    assert result.status_code == 200 and result.get_body() == b"source bytes"
    assert result.headers["Cache-Control"] == "private, no-store"


async def test_keyword_mode_does_not_call_embedding(caller, monkeypatch):
    embedding = Mock()
    monkeypatch.setattr(api, "embed", embedding)
    monkeypatch.setattr(api, "Search", Mock(return_value=SimpleNamespace(query=Mock(return_value=[]))))
    result = await function(api.search_index)(
        req(params={"q": "contract", "mode": "keyword", "semantic": "false"})
    )
    assert result.status_code == 200
    embedding.assert_not_called()


async def test_status_does_not_disclose_cross_tenant_job(caller):
    client = SimpleNamespace(
        get_status=AsyncMock(
            return_value=SimpleNamespace(
                to_json=lambda: {
                    "input": {"scope": {"tenant_id": "other"}, "index_name": "documents-v2"},
                    "runtimeStatus": "Running",
                }
            )
        )
    )
    result = await function(api.status_id)(req(route_params={"id": "job"}), client)
    assert result.status_code == 404


async def test_non_operator_cannot_get_orchestration_history(caller):
    client = SimpleNamespace(get_status=AsyncMock())
    result = await function(api.status_id)(
        req(params={"show_history": "true"}, route_params={"id": "job"}), client
    )
    assert result.status_code == 403
    client.get_status.assert_not_called()


async def test_status_omits_input_error_and_history(caller):
    data = {
        "input": {"scope": {"tenant_id": "tenant-a"}, "index_name": "documents-v2"},
        "runtimeStatus": "Failed",
        "output": "sensitive downstream exception",
        "historyEvents": ["private"],
    }
    client = SimpleNamespace(get_status=AsyncMock(return_value=SimpleNamespace(to_json=lambda: data)))
    result = await function(api.status_id)(req(route_params={"id": "job"}), client)
    assert result.status_code == 200
    body = json.loads(result.get_body())
    assert not {"input", "output", "historyEvents"}.intersection(body)
