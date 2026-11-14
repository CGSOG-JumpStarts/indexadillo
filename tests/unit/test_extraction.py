from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from core import models
from core.config import ProcessingProfile


def test_layout_uploads_bytes_with_markdown_and_unicode_spans(monkeypatch):
    content = "# Title\n\n猫 table\n"
    result = SimpleNamespace(
        content=content,
        pages=[SimpleNamespace(page_number=1, spans=[SimpleNamespace(offset=0, length=len(content))])],
    )
    begin = Mock(return_value=SimpleNamespace(result=Mock(return_value=result)))
    monkeypatch.setattr(models, "layout_client", lambda _: SimpleNamespace(begin_analyze_document=begin))
    actual = models.extract(b"source bytes", ProcessingProfile().extraction)
    assert actual == {"content": content, "pages": [{"page": 1, "start": 0, "end": len(content)}]}
    assert begin.call_args.kwargs["body"] == b"source bytes"
    assert begin.call_args.kwargs["output_content_format"] == "markdown"
    assert begin.call_args.kwargs["string_index_type"] == "unicodeCodePoint"


def content_config():
    return ProcessingProfile.model_validate(
        {
            "extraction": {
                "provider": "content-understanding",
                "api_version": "2025-11-01",
                "analyzer": "custom-layout",
            }
        }
    ).extraction


def test_content_understanding_polls_same_host_and_preserves_known_page_provenance(monkeypatch):
    monkeypatch.setenv("CONTENT_UNDERSTANDING_ENDPOINT", "https://cu.example.test")
    request = Mock(
        side_effect=[
            httpx.Response(202, headers={"Operation-Location": "https://cu.example.test/result/1"}),
            httpx.Response(
                200,
                json={
                    "status": "Succeeded",
                    "result": {
                        "contents": [
                            {"markdown": "# Page 2", "startPageNumber": 2, "endPageNumber": 2},
                            {"markdown": "Multi-page content", "startPageNumber": 3, "endPageNumber": 5},
                        ]
                    },
                },
            ),
        ]
    )
    monkeypatch.setattr(models, "request", request)
    value = models.extract(b"pdf", content_config())
    assert value["content"] == "# Page 2\n\nMulti-page content"
    assert value["pages"] == [{"page": 2, "start": 0, "end": 8}]
    post = request.call_args_list[0]
    assert post.args[1].endswith("/contentunderstanding/analyzers/custom-layout:analyzeBinary")
    assert post.kwargs["params"]["api-version"] == "2025-11-01"
    assert post.kwargs["retry_safe"] is False


def test_content_understanding_does_not_forward_credentials_to_foreign_polling_host(monkeypatch):
    monkeypatch.setenv("CONTENT_UNDERSTANDING_ENDPOINT", "https://cu.example.test")
    request = Mock(
        return_value=httpx.Response(
            202, headers={"Operation-Location": "https://other.example.test/result/1"}
        )
    )
    monkeypatch.setattr(models, "request", request)
    with pytest.raises(ValueError, match="operation location"):
        models.extract(b"pdf", content_config())
    assert request.call_count == 1


def test_content_understanding_failure_is_not_an_empty_success(monkeypatch):
    monkeypatch.setenv("CONTENT_UNDERSTANDING_ENDPOINT", "https://cu.example.test")
    request = Mock(
        side_effect=[
            httpx.Response(202, headers={"Operation-Location": "https://cu.example.test/result/1"}),
            httpx.Response(200, json={"status": "Failed"}),
        ]
    )
    monkeypatch.setattr(models, "request", request)
    with pytest.raises(RuntimeError, match="analysis failed"):
        models.extract(b"pdf", content_config())
