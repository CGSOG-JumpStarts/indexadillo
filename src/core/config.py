"""Validated deployment configuration. No service calls at import time."""

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmbeddingConfig(StrictModel):
    deployment: str = "embedding"
    model: Literal["text-embedding-3-large", "text-embedding-3-small"] = "text-embedding-3-large"
    dimensions: int = Field(default=3072, ge=256, le=3072)
    max_batch_tokens: int = Field(default=16000, ge=512, le=100000)
    max_batch_items: int = Field(default=32, ge=1, le=2048)

    @model_validator(mode="after")
    def dimensions_supported(self):
        if self.model == "text-embedding-3-small" and self.dimensions > 1536:
            raise ValueError("text-embedding-3-small supports at most 1536 dimensions")
        return self


class ExtractionConfig(StrictModel):
    provider: Literal["document-intelligence", "content-understanding", "text"] = "document-intelligence"
    api_version: str = "2024-11-30"
    analyzer: str = "prebuilt-layout"
    output: Literal["markdown"] = "markdown"
    max_bytes: int = Field(default=50_000_000, ge=1, le=500_000_000)

    @model_validator(mode="after")
    def stable_versions(self):
        if self.provider == "document-intelligence" and self.api_version != "2024-11-30":
            raise ValueError("Document Intelligence production API must be 2024-11-30")
        if self.provider == "content-understanding" and self.api_version != "2025-11-01":
            raise ValueError("Content Understanding production API must be 2025-11-01")
        return self


class ChunkingConfig(StrictModel):
    strategy: Literal["section-aware"] = "section-aware"
    target_tokens: int = Field(default=512, ge=64, le=4096)
    overlap_tokens: int = Field(default=64, ge=0)
    encoding: Literal["cl100k_base"] = "cl100k_base"
    max_chunks: int = Field(default=512, ge=1, le=2000)

    @model_validator(mode="after")
    def overlap_supported(self):
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        return self


class IndexConfig(StrictModel):
    schema_version: int = Field(default=2, ge=2)
    api_version: Literal["2026-04-01"] = "2026-04-01"
    compression: Literal["none", "scalar", "binary"] = "scalar"


class EnrichmentConfig(StrictModel):
    enabled: bool = False
    deployment: str = ""
    model: Literal["gpt-6-luna", "gpt-6.1-sol"] = "gpt-6-luna"
    fallback_deployment: str = ""
    fallback_model: Literal["gpt-6-luna", "gpt-6.1-sol"] = "gpt-6.1-sol"
    reasoning_effort: Literal["low", "medium", "high"] = "low"
    verbosity: Literal["low", "medium", "high"] = "low"
    max_input_tokens: int = Field(default=8000, ge=512, le=32000)
    max_output_tokens: int = Field(default=2048, ge=256, le=16000)

    @model_validator(mode="after")
    def deployment_required(self):
        if self.enabled and not self.deployment:
            raise ValueError("Enabled enrichment needs an explicit Azure deployment")
        return self


class ProcessingProfile(StrictModel):
    profile_id: str = "documents-v2"
    embedding: EmbeddingConfig = EmbeddingConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    index: IndexConfig = IndexConfig()
    enrichment: EnrichmentConfig = EnrichmentConfig()

    def fingerprint(self, *sections: str) -> str:
        data = self.model_dump()
        if sections:
            data = {key: data[key] for key in sections}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]


class TenantScope(StrictModel):
    tenant_id: str
    prefix: str
    indexes: list[str] = Field(min_length=1)
    default_groups: list[str] = Field(default_factory=list)
    query_alias: str | None = None

    @model_validator(mode="after")
    def validate_routing(self):
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", self.tenant_id):
            raise ValueError("Invalid tenant identifier")
        if not self.prefix or not self.prefix.endswith("/") or ".." in self.prefix.split("/"):
            raise ValueError("Each tenant needs a nonempty prefix ending in /")
        for name in self.indexes + ([self.query_alias] if self.query_alias else []):
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,126}[a-z0-9]", name):
                raise ValueError("Invalid search index name")
        return self


@lru_cache
def profile() -> ProcessingProfile:
    path = Path(
        os.getenv("PROCESSING_PROFILE", str(Path(__file__).parents[1] / "profiles/documents-v2.yaml"))
    )
    return ProcessingProfile.model_validate(yaml.safe_load(path.read_text()))


@lru_cache
def scopes() -> dict[str, TenantScope]:
    raw = json.loads(os.environ["TENANT_SCOPES_JSON"])
    result = {key: TenantScope.model_validate(value) for key, value in raw.items()}
    prefixes = [value.prefix for value in result.values()]
    if any(a.startswith(b) or b.startswith(a) for i, a in enumerate(prefixes) for b in prefixes[i + 1 :]):
        raise ValueError("Tenant source prefixes must not overlap")
    if len({value.tenant_id for value in result.values()}) != len(result):
        raise ValueError("Tenant identifiers must be unique")
    return result


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"Missing configuration: {name}")
    return value
