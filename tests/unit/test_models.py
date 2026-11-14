from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from core import azure, models
from core.config import ProcessingProfile


def test_embeddings_are_sorted_by_response_index_and_dimensions_checked(monkeypatch):
    config = ProcessingProfile().model_copy(
        update={"embedding": ProcessingProfile().embedding.model_copy(update={"dimensions": 256})}
    )
    create = Mock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[2.0] * 256),
                SimpleNamespace(index=0, embedding=[1.0] * 256),
            ],
            usage=SimpleNamespace(total_tokens=2),
        )
    )
    monkeypatch.setattr(
        models, "openai_client", lambda _: SimpleNamespace(embeddings=SimpleNamespace(create=create))
    )
    result = models.embed(["first", "second"], config)
    assert result[0][0] == 1 and result[1][0] == 2
    assert create.call_args.kwargs["dimensions"] == 256
    create.return_value.data[0].embedding = [0.0]
    with pytest.raises(ValueError, match="dimensions"):
        models.embed(["first", "second"], config)


def test_disabled_enrichment_never_calls_model(monkeypatch):
    client = Mock()
    monkeypatch.setattr(models, "openai_client", client)
    assert models.enrich("content", ProcessingProfile()) == {}
    client.assert_not_called()


def test_responses_enrichment_is_stateless_strict_and_escalates_low_confidence(monkeypatch):
    profile = ProcessingProfile.model_validate(
        {
            "enrichment": {
                "enabled": True,
                "deployment": "small",
                "fallback_deployment": "large",
            }
        }
    )
    usage = SimpleNamespace(
        input_tokens=10, output_tokens=5, input_tokens_details=SimpleNamespace(cached_tokens=0)
    )

    def result(confidence):
        return SimpleNamespace(
            status="completed",
            output_text='{"title":"Report","category":"report",'
            '"summary":"Summary","keywords":[],"confidence":' + str(confidence) + "}",
            usage=usage,
        )

    create = Mock(side_effect=[result(0.5), result(0.9)])
    monkeypatch.setattr(
        models, "openai_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    assert models.enrich("document", profile)["confidence"] == 0.9
    assert [c.kwargs["model"] for c in create.call_args_list] == ["small", "large"]
    assert all(
        c.kwargs["store"] is False and c.kwargs["text"]["format"]["strict"] for c in create.call_args_list
    )
    assert all("previous_response_id" not in c.kwargs for c in create.call_args_list)


def test_incomplete_response_cannot_publish_metadata(monkeypatch):
    profile = ProcessingProfile.model_validate({"enrichment": {"enabled": True, "deployment": "small"}})
    create = Mock(return_value=SimpleNamespace(status="incomplete"))
    monkeypatch.setattr(
        models, "openai_client", lambda: SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    with pytest.raises(RuntimeError, match="did not complete"):
        models.enrich("document", profile)


def test_retry_after_is_honored_and_original_headers_preserved(monkeypatch):
    client = Mock()
    client.request.side_effect = [httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200)]
    monkeypatch.setattr(azure, "transport", lambda: client)
    monkeypatch.setattr(
        azure, "credential", lambda _: SimpleNamespace(get_token=lambda _: SimpleNamespace(token="redacted"))
    )
    sleep = Mock()
    monkeypatch.setattr(azure.time, "sleep", sleep)
    azure.request(
        "POST", "https://azure.example.test", headers={"Content-Type": "application/pdf"}, content=b"data"
    )
    sleep.assert_called_once_with(3.0)
    assert all(
        c.kwargs["headers"]["Content-Type"] == "application/pdf" for c in client.request.call_args_list
    )


def test_text_extraction_preserves_spacing_and_unicode():
    config = ProcessingProfile.model_validate({"extraction": {"provider": "text"}}).extraction
    value = "# Heading\n\nFirst line.\nSecond line. 猫"
    document = models.extract(value.encode(), config)
    assert document["content"] == value
    assert document["pages"][0]["end"] == len(value)


def test_azure_v1_client_uses_managed_identity_token_provider(monkeypatch):
    models.openai_client.cache_clear()
    identity = object()
    provider = Mock()
    token_provider = Mock(return_value=provider)
    constructor = Mock(return_value=SimpleNamespace(close=Mock()))
    monkeypatch.setattr(models, "credential", lambda _: identity)
    monkeypatch.setattr(models, "get_bearer_token_provider", token_provider)
    monkeypatch.setattr(models, "OpenAI", constructor)
    try:
        models.openai_client("query")
        token_provider.assert_called_once_with(identity, "https://ai.azure.com/.default")
        assert constructor.call_args.kwargs["base_url"] == "https://models.example.test/openai/v1/"
        assert constructor.call_args.kwargs["api_key"] is provider
        assert "api_version" not in constructor.call_args.kwargs
    finally:
        models.openai_client.cache_clear()


def test_lost_lease_prevents_a_downstream_retry(monkeypatch):
    from core.storage import Busy

    client = Mock()
    monkeypatch.setattr(azure, "transport", lambda: client)
    guard = SimpleNamespace(check=Mock(side_effect=Busy()))
    with pytest.raises(Busy):
        azure.request("POST", "https://azure.example.test", lease_guard=guard)
    client.request.assert_not_called()
