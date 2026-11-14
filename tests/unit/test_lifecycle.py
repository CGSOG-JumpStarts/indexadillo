import pytest

from core.lifecycle import publish, record_failure
from core.storage import document_id


def test_full_path_and_tenant_are_part_of_document_identity():
    ids = {
        document_id(tenant, "account", "source", path)
        for tenant in ("one", "two")
        for path in ("a/report.pdf", "b/report.pdf")
    }
    assert len(ids) == 4


def test_replay_is_idempotent_and_shrinking_document_removes_old_chunks(ref, storage, search):
    assert publish(ref, storage, search) == {"status": "published", "chunks": 2}
    first_ids = set(search.documents)
    assert publish(ref, storage, search)["status"] == "unchanged"
    updated = {**ref, "etag": "v2", "artifact": "second"}
    storage.sources[ref["source_name"]] = "v2"
    storage.write("artifacts", "second", {"chunks": [storage.chunk(0)]})
    assert publish(updated, storage, search)["chunks"] == 1
    assert not first_ids.intersection(search.documents)
    assert len(search.documents) == 1
    manifest = storage.read("manifests", storage.manifest_name(ref))
    assert set(manifest["chunk_ids"]) == set(search.documents)
    assert manifest["pending_ids"] == []


def test_delete_removes_all_generations_and_tombstones(ref, storage, search):
    publish(ref, storage, search)
    del storage.sources[ref["source_name"]]
    assert publish({**ref, "operation": "delete"}, storage, search)["status"] == "deleted"
    assert not search.documents
    assert publish({**ref, "operation": "delete"}, storage, search)["status"] == "deleted"
    assert storage.read("manifests", storage.manifest_name(ref))["state"] == "deleted"


def test_late_delete_cannot_remove_recreated_source(ref, storage, search):
    publish(ref, storage, search)
    storage.sources[ref["source_name"]] = "v2"
    assert publish({**ref, "operation": "delete"}, storage, search)["status"] == "superseded"
    assert len(search.documents) == 2


def test_stale_version_never_publishes(ref, storage, search):
    storage.sources[ref["source_name"]] = "newer"
    assert publish(ref, storage, search)["status"] == "superseded"
    assert not search.documents


def test_interrupted_upload_is_recovered_and_obsolete_pending_keys_removed(ref, storage, search):
    search.interrupt_after = 1
    with pytest.raises(TimeoutError):
        publish(ref, storage, search)
    partial_ids = set(search.documents)
    pending = storage.read("manifests", storage.manifest_name(ref))
    assert partial_ids.issubset(pending["pending_ids"])
    assert pending["state"] == "publishing"
    storage.sources[ref["source_name"]] = "v2"
    storage.write("artifacts", "new", {"chunks": [storage.chunk(0)]})
    search.interrupt_after = None
    publish({**ref, "etag": "v2", "artifact": "new"}, storage, search)
    assert not partial_ids.intersection(search.documents)
    assert len(search.documents) == 1


def test_source_changes_during_upload_removes_unpublished_generation(ref, storage, search):
    search.after_write = lambda: storage.sources.update({ref["source_name"]: "v2"})
    assert publish(ref, storage, search)["status"] == "superseded"
    assert not search.documents


def test_failure_record_preserves_keys_needed_for_cleanup(ref, storage, search):
    publish(ref, storage, search)
    original = set(search.documents)
    record_failure(ref, storage=storage)
    manifest = storage.read("manifests", storage.manifest_name(ref))
    assert set(manifest["chunk_ids"]) == original
    assert manifest["state"] == "failed"


def test_empty_replacement_removes_all_previous_content(ref, storage, search):
    publish(ref, storage, search)
    storage.sources[ref["source_name"]] = "v2"
    storage.write("artifacts", "empty", {"chunks": []})
    publish({**ref, "etag": "v2", "artifact": "empty"}, storage, search)
    assert not search.documents


def test_managed_knowledge_binding_rejects_restricted_publication(ref, storage, search):
    storage.write("registry", "documents-v2.json", {"knowledge_tenant": "tenant-a"})
    with pytest.raises(ValueError, match="Knowledge-source"):
        publish({**ref, "visibility": "restricted", "allowed_groups": ["group"]}, storage, search)
    assert not search.documents


def test_reconciliation_removes_unknown_orphans_from_an_interrupted_publisher(ref, storage, search):
    publish(ref, storage, search)
    expected = set(search.documents)
    search.documents["orphan"] = {"id": "orphan", "document_id": ref["document_id"]}
    assert publish(ref, storage, search)["status"] == "unchanged"
    assert set(search.documents) == expected
