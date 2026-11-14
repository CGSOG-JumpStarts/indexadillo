import pytest
from pydantic import ValidationError

from core.chunking import chunk_document, encoder
from core.config import ChunkingConfig, ProcessingProfile
from core.models import embedding_batches


def test_chunks_preserve_unicode_and_original_page_spans():
    text = "# 第一章\n\n" + "猫😀 café action. " * 200 + "\n# Second\n\n" + "Other words. " * 50
    split = text.index("# Second")
    pages = [{"page": 1, "start": 0, "end": split}, {"page": 2, "start": split, "end": len(text)}]
    config = ChunkingConfig(target_tokens=64, overlap_tokens=8)
    chunks = chunk_document({"content": text, "pages": pages}, config)
    assert len(chunks) > 2
    assert all(text[c["start"] : c["end"]] == c["text"] for c in chunks)
    assert all(c["token_count"] <= 64 for c in chunks)
    assert chunks[0]["pages"] == [1] and chunks[-1]["pages"] == [2]
    assert chunks[-1]["end"] == len(text)


def test_exact_page_boundary_does_not_claim_previous_page():
    text = "# One\na\n# Two\nb"
    boundary = text.index("# Two")
    chunks = chunk_document(
        {
            "content": text,
            "pages": [
                {"page": 1, "start": 0, "end": boundary},
                {"page": 2, "start": boundary, "end": len(text)},
            ],
        },
        ChunkingConfig(),
    )
    assert [c["pages"] for c in chunks] == [[1], [2]]


def test_empty_text_and_missing_page_provenance():
    assert chunk_document({"content": "", "pages": []}, ChunkingConfig()) == []
    assert chunk_document({"content": "hello", "pages": []}, ChunkingConfig())[0]["pages"] == []


def test_chunk_limit_prevents_unbounded_document_memory():
    with pytest.raises(ValueError, match="chunk limit"):
        chunk_document(
            {"content": "word " * 1000, "pages": []},
            ChunkingConfig(target_tokens=64, overlap_tokens=0, max_chunks=2),
        )


def test_profile_rejects_incompatible_dimensions_and_preview_extraction():
    with pytest.raises(ValidationError):
        ProcessingProfile.model_validate(
            {"embedding": {"model": "text-embedding-3-small", "dimensions": 3072}}
        )
    with pytest.raises(ValidationError):
        ProcessingProfile.model_validate({"extraction": {"api_version": "2026-06-01-preview"}})
    with pytest.raises(ValidationError):
        ChunkingConfig(target_tokens=64, overlap_tokens=64)


def test_embedding_batches_obey_tokens_and_item_count():
    config = ProcessingProfile().embedding.model_copy(update={"max_batch_tokens": 512, "max_batch_items": 2})
    texts = ["hello " * 180] * 5
    batches = list(embedding_batches(texts, config))
    assert sum(len(batch) for batch in batches) == 5
    assert all(
        len(batch) <= 2 and sum(len(encoder().encode(text)) for text in batch) <= 512 for batch in batches
    )
    with pytest.raises(ValueError):
        list(embedding_batches(["hello " * 9000], config))
