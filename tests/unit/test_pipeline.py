import json

import httpx
from openai import OpenAI

from activities import chuncking, cracking, embedding
from core import models
from core.config import ProcessingProfile
from core.lifecycle import publish


def test_actual_activities_and_openai_sdk_publish_and_reuse_content_cache(ref, storage, search, monkeypatch):
    profile = ProcessingProfile.model_validate(
        {"extraction": {"provider": "text"}, "embedding": {"dimensions": 256}}
    )
    ref = {**ref, "profile": profile.model_dump()}
    calls = []

    def handle(request):
        assert request.url.path == "/openai/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-only-token"
        body = json.loads(request.content)
        assert body["model"] == "embedding" and body["dimensions"] == 256
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": [
                    {"object": "embedding", "index": i, "embedding": [0.1] * 256}
                    for i in range(len(body["input"]))
                ],
                "usage": {"prompt_tokens": 20, "total_tokens": 20},
            },
        )

    client = OpenAI(
        base_url="https://models.example.test/openai/v1/",
        api_key="test-only-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    monkeypatch.setattr(models, "openai_client", lambda *args: client)
    for module in (cracking, chuncking, embedding, models):
        monkeypatch.setattr(module, "store", lambda: storage)
    activities = [cracking.document_cracking, chuncking.chunking, embedding.embedding]

    def run(value):
        for activity in activities:
            value = activity._function.get_user_function()(value)
            assert "artifact" in value and "chunks" not in value and "content" not in value
            assert "?" not in value["artifact"]
        return value

    try:
        result = run(ref)
        assert publish(result, storage, search)["status"] == "published"
        assert len(search.documents) == 1
        assert next(iter(search.documents.values()))["content"].startswith("# Report")
        # ETag changes without content changes reuse all model results.
        storage.sources[ref["source_name"]] = "v2"
        updated = run({**ref, "etag": "v2"})
        assert publish(updated, storage, search)["status"] == "published"
        assert len(calls) == 1
    finally:
        client.close()


def test_activity_failure_does_not_serialize_service_response_content(ref, monkeypatch):
    import pytest

    from core.activity import ActivityFailure

    monkeypatch.setattr(
        cracking, "store", lambda: (_ for _ in ()).throw(RuntimeError("sensitive source text"))
    )
    with pytest.raises(ActivityFailure) as exc:
        cracking.document_cracking._function.get_user_function()(ref)
    assert "sensitive" not in str(exc.value)
    assert exc.value.__suppress_context__
