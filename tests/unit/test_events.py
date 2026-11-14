import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import azure.functions as func

import function_app as api
from activities.listblob import list_blobs_chunk


async def test_committed_block_upload_is_processed_and_duplicate_event_is_not_rescheduled(monkeypatch):
    props = SimpleNamespace(etag="current-etag", metadata={})
    monkeypatch.setattr(api, "store", lambda: SimpleNamespace(current=lambda _: props))
    event = {
        "id": "event-1",
        "eventType": "Microsoft.Storage.BlobCreated",
        "data": {
            "api": "PutBlockList",
            "url": "https://sourceaccount.blob.core.windows.net/source/tenants/a/report.pdf",
        },
    }
    client = SimpleNamespace(get_status=AsyncMock(return_value=None), start_new=AsyncMock())
    function = inspect.unwrap(api.index_event_grid._function.get_user_function())
    message = func.QueueMessage(body=json.dumps(event).encode())
    await function(message, client)
    assert client.start_new.call_args.kwargs["client_input"]["source_name"] == "tenants/a/report.pdf"
    client.get_status.return_value = SimpleNamespace(runtime_status="Running")
    await function(message, client)
    assert client.start_new.call_count == 1


async def test_delete_event_carries_exact_path_and_not_a_prefix_scan(monkeypatch):
    monkeypatch.setattr(api, "store", lambda: SimpleNamespace(current=lambda _: None))
    client = SimpleNamespace(get_status=AsyncMock(return_value=None), start_new=AsyncMock())
    event = {
        "id": "deleted",
        "eventType": "Microsoft.Storage.BlobDeleted",
        "data": {
            "url": "https://sourceaccount.blob.core.windows.net/source/tenants/a/report.pdf",
        },
    }
    await inspect.unwrap(api.index_event_grid._function.get_user_function())(
        func.QueueMessage(body=json.dumps(event).encode()), client
    )
    ref = client.start_new.call_args.kwargs["client_input"]
    assert ref["operation"] == "delete" and ref["source_name"] == "tenants/a/report.pdf"


def test_empty_blob_listing_advances_prefix_without_stopping(monkeypatch):
    class Pages:
        continuation_token = None

        def __iter__(self):
            return iter([])

        def __next__(self):
            raise StopIteration

    pages = Pages()
    container = Mock()
    container.list_blobs.return_value.by_page.return_value = pages
    monkeypatch.setattr(
        "activities.listblob.blobs", lambda _: SimpleNamespace(get_container_client=lambda _: container)
    )
    function = inspect.unwrap(list_blobs_chunk._function.get_user_function())
    result = function({"job": {"prefix_list": ["empty/", "full/"], "parallel": 4}, "offset": 0})
    assert result == {"documents": [], "offset": 1, "token": None, "done": False}
