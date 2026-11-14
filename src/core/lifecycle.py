"""Recoverable publication under per-document leases.

Search has no multi-document transactions: reads can briefly see both generations.
A persisted pending set makes interrupted replacement and deletion recoverable.
"""

import logging
from datetime import UTC, datetime

from core.config import ProcessingProfile
from core.search import Search
from core.storage import Superseded, digest, store

log = logging.getLogger("indexadillo")


def timestamp():
    return datetime.now(UTC).isoformat()


def chunk_ids(manifest):
    return set((manifest or {}).get("chunk_ids", [])) | set((manifest or {}).get("pending_ids", []))


def search_documents(ref, chunks, metadata, storage):
    generation = digest([ref["etag"], ref["profile"]])[:24]
    for position, chunk in enumerate(chunks):
        pages = chunk["pages"]
        yield {
            "@search.action": "upload",
            "id": f"{ref['document_id']}-{generation}-{position}",
            "document_id": ref["document_id"],
            "tenant_id": ref["tenant_id"],
            "generation": generation,
            "profile_id": ref["profile"]["profile_id"],
            "visibility": ref["visibility"],
            "source_etag": ref["etag"],
            "context": chunk.get("context", ""),
            "allowed_groups": ref["allowed_groups"],
            "content": chunk["text"],
            "embedding": chunk["embedding"],
            "title": metadata.get("title") or ref["source_name"].rsplit("/", 1)[-1],
            "category": metadata.get("category", ""),
            "summary": metadata.get("summary", ""),
            "keywords": metadata.get("keywords", []),
            "sourcefile": ref["source_name"],
            "sourcepages": ref["source_name"] + (f"#page={pages[0]}" if pages else ""),
            "pages": pages,
            "start": chunk["start"],
            "end": chunk["end"],
            "storageUrl": storage.source_url(ref),
        }


def publish(ref, storage=None, search=None):
    storage = storage or store()
    profile = ProcessingProfile.model_validate(ref["profile"])
    search = search or Search(profile)
    key = storage.manifest_name(ref)
    with storage.lock(f"documents/{key}") as guard:
        manifest = storage.read("manifests", key) or {}
        if ref.get("operation") == "delete":
            if storage.current(ref) is not None:
                return {"status": "superseded"}
            known = chunk_ids(manifest) | set(search.keys(ref["index_name"], ref["document_id"], guard))
            search.delete(ref["index_name"], sorted(known), guard)
            guard.check()
            storage.write(
                "manifests",
                key,
                {
                    **manifest,
                    "document_id": ref["document_id"],
                    "source_name": ref["source_name"],
                    "tenant_id": ref["tenant_id"],
                    "index_name": ref["index_name"],
                    "state": "deleted",
                    "chunk_ids": [],
                    "pending_ids": [],
                    "updated_at": timestamp(),
                },
            )
            return {"status": "deleted"}
        try:
            storage.assert_current(ref)
        except Superseded:
            return {"status": "superseded"}
        registry = storage.read("registry", f"{ref['index_name']}.json") or {}
        if registry.get("knowledge_tenant") and (
            ref["visibility"] != "tenant" or ref["tenant_id"] != registry["knowledge_tenant"]
        ):
            raise ValueError("Knowledge-source indexes cannot contain restricted or cross-tenant documents")
        fingerprint = digest([ref["etag"], profile.fingerprint(), ref["allowed_groups"], ref["visibility"]])
        if manifest.get("fingerprint") == fingerprint and manifest.get("state") == "published":
            extras = set(search.keys(ref["index_name"], ref["document_id"], guard)) - set(
                manifest["chunk_ids"]
            )
            search.delete(ref["index_name"], sorted(extras), guard)
            return {"status": "unchanged"}
        artifact = storage.read("artifacts", ref["artifact"])
        if artifact is None:
            raise ValueError("Embedding artifact is missing")
        documents = list(search_documents(ref, artifact["chunks"], artifact.get("metadata", {}), storage))
        ids = {doc["id"] for doc in documents}
        pending = {
            **manifest,
            "document_id": ref["document_id"],
            "source_name": ref["source_name"],
            "tenant_id": ref["tenant_id"],
            "index_name": ref["index_name"],
            "state": "publishing",
            "pending_ids": sorted(chunk_ids(manifest) | ids),
            "updated_at": timestamp(),
            "etag": ref["etag"],
        }
        guard.check()
        storage.write("manifests", key, pending)
        search.write(ref["index_name"], documents, guard)
        try:
            storage.assert_current(ref)
        except Superseded:
            search.delete(ref["index_name"], sorted(ids - set(manifest.get("chunk_ids", []))), guard)
            guard.check()
            storage.write("manifests", key, {**pending, "state": "superseded"})
            return {"status": "superseded"}
        known = chunk_ids(pending) | set(search.keys(ref["index_name"], ref["document_id"], guard))
        search.delete(ref["index_name"], sorted(known - ids), guard)
        guard.check()
        storage.write(
            "manifests",
            key,
            {
                **pending,
                "state": "published",
                "fingerprint": fingerprint,
                "profile_fingerprint": profile.fingerprint(),
                "chunk_ids": sorted(ids),
                "pending_ids": [],
                "published_at": timestamp(),
                "error_type": None,
            },
        )
        modified = ref.get("source_modified_at")
        freshness = (
            max(0, (datetime.now(UTC) - datetime.fromisoformat(modified)).total_seconds())
            if modified
            else None
        )
        log.info(
            "document_published document_id=%s chunks=%s freshness_seconds=%s",
            ref["document_id"],
            len(ids),
            freshness,
        )
        return {"status": "published", "chunks": len(ids)}


def record_failure(ref, error_type="ProcessingError", storage=None):
    storage = storage or store()
    key = storage.manifest_name(ref)
    with storage.lock(f"documents/{key}") as guard:
        value = storage.read("manifests", key) or {}
        guard.check()
        storage.write(
            "manifests",
            key,
            {
                **value,
                "document_id": ref["document_id"],
                "tenant_id": ref["tenant_id"],
                "source_name": ref["source_name"],
                "index_name": ref["index_name"],
                "state": "failed",
                "error_type": error_type,
                "failed_stage": ref.get("failed_stage", "unknown"),
                "updated_at": timestamp(),
            },
        )
        log.error("document_failed document_id=%s error_type=%s", ref["document_id"], error_type)
