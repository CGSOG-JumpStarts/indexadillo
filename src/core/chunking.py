"""Markdown section boundaries with bounded tokens and original character spans."""

import os
import re
from functools import lru_cache
from pathlib import Path

import tiktoken


@lru_cache
def encoder(name="cl100k_base"):
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(__file__).parents[1] / "tokenizer"))
    return tiktoken.get_encoding(name)


def source_pages(start: int, end: int, pages: list[dict]) -> list[int]:
    result = sorted({page["page"] for page in pages if page["start"] < end and page["end"] > start})
    return result


def chunk_document(document: dict, config) -> list[dict]:
    text = document["content"]
    enc = encoder(config.encoding)
    boundaries = [0] + [m.start() for m in re.finditer(r"(?m)^#{1,6} +", text) if m.start()] + [len(text)]
    chunks = []
    for section_start, section_end in zip(boundaries[:-1], boundaries[1:], strict=True):
        segment = text[section_start:section_end]
        tokens = enc.encode(segment, disallowed_special=())
        if not tokens:
            continue
        # Token byte offsets avoid character corruption when Unicode spans multiple tokens.
        token_bytes = [enc.decode_single_token_bytes(token) for token in tokens]
        offsets = [0]
        for piece in token_bytes:
            offsets.append(offsets[-1] + len(piece))
        raw = segment.encode("utf-8")
        cursor = 0
        while cursor < len(tokens):
            stop = min(cursor + config.target_tokens, len(tokens))
            while stop < len(tokens) and (raw[offsets[stop]] & 0xC0) == 0x80:
                stop -= 1
            if stop <= cursor:
                raise ValueError("Token target cannot contain a Unicode character")
            value = raw[offsets[cursor] : offsets[stop]].decode("utf-8")
            start = section_start + len(raw[: offsets[cursor]].decode("utf-8"))
            end = start + len(value)
            if value.strip():
                if len(chunks) >= config.max_chunks:
                    raise ValueError("Document exceeds configured chunk limit")
                heading = segment.splitlines()[0] if segment.startswith("#") else ""
                before = text[section_start:start]
                headers = list(re.finditer(r"(?m)^(\|.*\|)\n(\|[ :|\-]+\|)\s*$", before))
                table_header = headers[-1].group(0) if headers and value.lstrip().startswith("|") else ""
                context = "\n".join(part for part in (heading if cursor else "", table_header) if part)
                context = enc.decode(enc.encode(context, disallowed_special=())[:256])
                chunks.append(
                    {
                        "text": value,
                        "start": start,
                        "end": end,
                        "context": context,
                        "pages": source_pages(start, end, document.get("pages", [])),
                        "token_count": stop - cursor,
                    }
                )
            if stop == len(tokens):
                break
            cursor = max(cursor + 1, stop - config.overlap_tokens)
            while cursor < stop and (raw[offsets[cursor]] & 0xC0) == 0x80:
                cursor += 1
    return chunks
