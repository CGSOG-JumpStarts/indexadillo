"""Bounded enumeration; an empty prefix never ends other prefixes."""

import os

from application.app import app
from core.activity import safe_activity
from core.config import required
from core.storage import blobs, document_id, store


def descriptor(job, name, props=None, operation="index"):
    scope = job["scope"]
    metadata = (props.metadata or {}) if props else {}
    groups = [value.strip() for value in metadata.get("allowed_groups", "").split(",") if value.strip()]
    if not groups:
        groups = scope.get("default_groups", [])
    visibility = metadata.get("visibility", "restricted" if groups else "tenant")
    if scope.get("default_groups"):
        visibility = "restricted"
    account = required("SOURCE_STORAGE_ACCOUNT_NAME")
    return {
        "document_id": document_id(
            scope["tenant_id"], account, os.getenv("BLOB_CONTAINER_NAME", "source"), name
        ),
        "tenant_id": scope["tenant_id"],
        "source_modified_at": props.last_modified.isoformat()
        if props and getattr(props, "last_modified", None)
        else None,
        "source_name": name,
        "etag": str(props.etag) if props else "",
        "allowed_groups": sorted(set(groups)),
        "visibility": visibility,
        "operation": operation,
        "index_name": job["index_name"],
        "profile": job["profile"],
    }


@app.function_name(name="list_blobs_chunk")
@app.activity_trigger(input_name="params")
@safe_activity
def list_blobs_chunk(params: dict):
    job = params["job"]
    offset, token = params.get("offset", 0), params.get("token")
    prefixes = job["prefix_list"]
    if offset >= len(prefixes):
        return {"documents": [], "offset": offset, "token": None, "done": True}
    container = blobs(required("SOURCE_STORAGE_ACCOUNT_NAME")).get_container_client(
        os.getenv("BLOB_CONTAINER_NAME", "source")
    )
    pages = container.list_blobs(
        name_starts_with=prefixes[offset], include=["metadata"], results_per_page=job["parallel"]
    ).by_page(continuation_token=token)
    documents = [descriptor(job, item.name, item) for item in next(pages, [])]
    token = pages.continuation_token
    if not token:
        offset += 1
    return {"documents": documents, "offset": offset, "token": token, "done": offset >= len(prefixes)}


@app.function_name(name="list_missing_documents")
@app.activity_trigger(input_name="params")
@safe_activity
def list_missing_documents(params: dict):
    job = params["job"]
    storage = store()
    prefix = f"{job['scope']['tenant_id']}/{job['index_name']}/"
    pages = (
        storage.service.get_container_client("manifests")
        .list_blobs(name_starts_with=prefix, results_per_page=job["parallel"])
        .by_page(continuation_token=params.get("token"))
    )
    documents = []
    for blob in next(pages, []):
        manifest = storage.read("manifests", blob.name)
        if manifest and manifest.get("state") != "deleted":
            name = manifest["source_name"]
            if any(name.startswith(value) for value in job["prefix_list"]):
                ref = descriptor(job, name, operation="delete")
                if storage.current(ref) is None:
                    documents.append(ref)
    return {"documents": documents, "token": pages.continuation_token, "done": not pages.continuation_token}
