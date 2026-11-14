"""Authenticated HTTP API, private queue ingestion, reconciliation and history retention."""

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, unquote, urlsplit

import azure.functions as func
from azure.durable_functions import DurableOrchestrationClient, OrchestrationRuntimeStatus

from activities.chuncking import chunking  # noqa: F401
from activities.cracking import document_cracking  # noqa: F401
from activities.embedding import embedding  # noqa: F401
from activities.listblob import descriptor, list_blobs_chunk, list_missing_documents  # noqa: F401
from activities.search import add_documents, ensure_index_exists, record_document_failure  # noqa: F401
from application.app import app
from core.auth import AccessDenied, authorize, current_source_allowed, permitted_index, permitted_prefixes
from core.config import profile, required, scopes
from core.models import embed
from core.search import Search
from core.storage import Superseded, digest, store
from orchestrators.index import index, index_document  # noqa: F401

log = logging.getLogger("indexadillo")


def response(value, status=200, headers=None):
    return func.HttpResponse(
        json.dumps(value), status_code=status, mimetype="application/json", headers=headers
    )


def error(exc):
    if isinstance(exc, AccessDenied):
        return response({"error": "unauthorized" if exc.status == 401 else "forbidden"}, exc.status)
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return response({"error": "invalid_request"}, 400)
    log.error("request_failed error_type=%s", type(exc).__name__)
    return response({"error": "service_unavailable"}, 503)


def job_for(scope, index_name, prefixes, reconcile=False):
    return {
        "scope": scope.model_dump(),
        "index_name": index_name,
        "prefix_list": prefixes,
        "reconcile": reconcile,
        "profile": profile().model_dump(),
        "parallel": max(1, min(32, int(os.getenv("BLOB_AMOUNT_PARALLEL", "4")))),
    }


@app.function_name(name="index_http")
@app.route(route="index", methods=[func.HttpMethod.POST])
@app.durable_client_input(client_name="client")
async def index_http(req: func.HttpRequest, client: DurableOrchestrationClient):
    try:
        principal = await asyncio.to_thread(authorize, req.headers, "Indexer")
        if len(req.get_body()) > 16384:
            return response({"error": "request_too_large"}, 413)
        body = req.get_json()
        if not isinstance(body, dict):
            raise ValueError("A JSON object is required")
        if set(body) - {"prefix_list", "index_name", "reconcile"}:
            raise ValueError("Unknown request properties")
        prefixes = body.get("prefix_list", [""])
        if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
            raise ValueError("prefix_list must contain strings")
        if not isinstance(body.get("reconcile", False), bool):
            raise ValueError("reconcile must be boolean")
        selected = permitted_index(principal, body.get("index_name"))
        prefixes = permitted_prefixes(principal.scope, prefixes)
        job = job_for(principal.scope, selected, prefixes, body.get("reconcile", False))
        instance_id = await client.start_new("index", client_input=job)
        location = f"/api/status/{instance_id}"
        return response(
            {"id": instance_id, "statusUrl": location}, 202, {"Location": location, "Retry-After": "5"}
        )
    except Exception as exc:
        return error(exc)


@app.function_name(name="status_id")
@app.route(route="status/{id}", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def status_id(req: func.HttpRequest, client: DurableOrchestrationClient):
    try:
        principal = await asyncio.to_thread(authorize, req.headers, "Indexer")
        details = req.params.get("show_history", "false").lower() == "true"
        if details and "Operator" not in principal.roles:
            raise AccessDenied()
        result = await client.get_status(
            req.route_params["id"], show_input=True, show_history=details, show_history_output=False
        )
        if not result:
            return response({"error": "not_found"}, 404)
        data = result.to_json()
        job = data.get("input") or {}
        if isinstance(job, str):
            job = json.loads(job)
        tenant = job.get("tenant_id") or job.get("scope", {}).get("tenant_id")
        if tenant != principal.scope.tenant_id or job.get("index_name") not in principal.scope.indexes:
            return response({"error": "not_found"}, 404)
        selected = {
            key: data.get(key)
            for key in ("instanceId", "runtimeStatus", "createdTime", "lastUpdatedTime", "customStatus")
        }
        if data.get("runtimeStatus") == "Completed":
            selected["output"] = data.get("output")
        if details:
            selected["historyEvents"] = data.get("historyEvents")
        return response(selected)
    except Exception as exc:
        return error(exc)


@app.function_name(name="status")
@app.route(route="status", methods=[func.HttpMethod.GET])
async def status(req: func.HttpRequest):
    # Global unbounded status enumeration is intentionally removed.
    try:
        await asyncio.to_thread(authorize, req.headers, "Operator")
        return response({"error": "Use /api/status/{id} or the operator dashboard"}, 400)
    except Exception as exc:
        return error(exc)


@app.function_name(name="search")
@app.route(route="search", methods=[func.HttpMethod.GET])
async def search_index(req: func.HttpRequest):
    try:
        principal = await asyncio.to_thread(authorize, req.headers, "Reader")
        query = req.params.get("q", "").strip()
        if not query or len(query) > 2048:
            raise ValueError("A query between 1 and 2048 characters is required")
        selected = permitted_index(principal, req.params.get("index_name"), for_query=True)
        mode = req.params.get("mode", "hybrid")
        if mode not in ("keyword", "vector", "hybrid"):
            raise ValueError("Unknown retrieval mode")
        semantic = req.params.get("semantic", "true").lower() == "true"
        top = int(req.params.get("top", "10"))
        if not 1 <= top <= 50:
            raise ValueError("top must be between 1 and 50")
        config = profile()
        vector = None
        if mode != "keyword":
            vector = (await asyncio.to_thread(embed, [query], config, identity="query"))[0]
        results = await asyncio.to_thread(
            Search(config, identity="query").query,
            selected,
            query,
            principal,
            vector=vector,
            mode=mode,
            semantic=semantic,
            top=top,
        )
        allowed_results = []
        source_props = {}
        for item in results:
            name = item["sourcefile"]
            if name not in source_props:
                source_props[name] = await asyncio.to_thread(store("query").current, {"source_name": name})
            if not current_source_allowed(principal, name, source_props[name], item["source_etag"]):
                continue
            item.pop("source_etag", None)
            item["citationUrl"] = f"/api/document/{item['document_id']}?index_name={selected}"
            if item.get("pages"):
                item["citationUrl"] += f"#page={item['pages'][0]}"
            allowed_results.append(item)
        return response(allowed_results)
    except Exception as exc:
        return error(exc)


@app.function_name(name="document")
@app.route(route="document/{id}", methods=[func.HttpMethod.GET])
async def download_document(req: func.HttpRequest):
    try:
        principal = await asyncio.to_thread(authorize, req.headers, "Reader")
        selected = permitted_index(principal, req.params.get("index_name"), for_query=True)
        identifier = req.route_params["id"]
        if not re.fullmatch(r"[0-9a-f]{64}", identifier):
            raise ValueError("Invalid document identifier")
        value = await asyncio.to_thread(
            Search(profile(), identity="query").document, selected, identifier, principal
        )
        if value is None:
            return response({"error": "not_found"}, 404)
        ref = {"source_name": value["sourcefile"], "etag": value["source_etag"]}
        props = await asyncio.to_thread(store("query").current, ref)
        if not current_source_allowed(principal, value["sourcefile"], props, value["source_etag"]):
            return response({"error": "not_found"}, 404)
        try:
            data = await asyncio.to_thread(store("query").source_bytes, ref, profile().extraction.max_bytes)
        except Superseded:
            return response({"error": "source_changed_reindex_pending"}, 409)
        filename = quote(value["sourcefile"].rsplit("/", 1)[-1], safe="")
        return func.HttpResponse(
            data,
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except Exception as exc:
        return error(exc)


@app.function_name(name="orchestration_health")
@app.route(route="orchestration_health", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def orchestration_health(req: func.HttpRequest, client: DurableOrchestrationClient):
    try:
        await asyncio.to_thread(authorize, req.headers, "Operator")
        await client.get_status("health-probe")
        return response({"status": "healthy"})
    except Exception as exc:
        return error(exc)


@app.function_name(name="index_event_grid")
@app.queue_trigger(arg_name="message", queue_name="ingestion-events", connection="SOURCE_EVENTS_STORAGE")
@app.durable_client_input(client_name="client")
async def index_event_grid(message: func.QueueMessage, client: DurableOrchestrationClient):
    payload = json.loads(message.get_body())
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        if event.get("eventType") not in ("Microsoft.Storage.BlobCreated", "Microsoft.Storage.BlobDeleted"):
            continue
        parsed = urlsplit(event["data"]["url"])
        account = required("SOURCE_STORAGE_ACCOUNT_NAME")
        container = os.getenv("BLOB_CONTAINER_NAME", "source")
        if parsed.scheme != "https" or parsed.netloc != f"{account}.blob.core.windows.net":
            raise ValueError("Unexpected event source")
        path = unquote(parsed.path).lstrip("/")
        if not path.startswith(f"{container}/"):
            raise ValueError("Unexpected source container")
        name = path[len(container) + 1 :]
        scope = next((value for value in scopes().values() if name.startswith(value.prefix)), None)
        if not scope:
            continue
        for selected in scope.indexes:
            job = job_for(scope, selected, [name])
            ref = descriptor(job, name, operation="delete")
            props = await asyncio.to_thread(store().current, ref)
            if event["eventType"].endswith("BlobCreated"):
                if props is None:
                    continue
                ref = descriptor(job, name, props)
            instance_id = f"event-{digest([event['id'], selected])}"
            existing = await client.get_status(instance_id)
            if existing is None:
                await client.start_new("index_document", instance_id=instance_id, client_input=ref)


@app.function_name(name="reconcile")
@app.timer_trigger(arg_name="timer", schedule="%RECONCILIATION_SCHEDULE%", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def reconcile(timer: func.TimerRequest, client: DurableOrchestrationClient):
    for scope in scopes().values():
        for selected in scope.indexes:
            instance_id = f"reconcile-{scope.tenant_id}-{selected}"
            previous = await client.get_status(instance_id)
            if previous and previous.runtime_status in (
                OrchestrationRuntimeStatus.Running,
                OrchestrationRuntimeStatus.Pending,
                OrchestrationRuntimeStatus.ContinuedAsNew,
                OrchestrationRuntimeStatus.Suspended,
            ):
                continue
            await client.start_new(
                "index", instance_id=instance_id, client_input=job_for(scope, selected, [scope.prefix], True)
            )


@app.function_name(name="purge_history")
@app.timer_trigger(arg_name="timer", schedule="0 30 3 * * *", run_on_startup=False)
@app.durable_client_input(client_name="client")
async def purge_history(timer: func.TimerRequest, client: DurableOrchestrationClient):
    days = max(1, int(os.getenv("HISTORY_RETENTION_DAYS", "14")))
    await client.purge_instance_history_by(
        datetime(2000, 1, 1, tzinfo=UTC),
        datetime.now(UTC) - timedelta(days=days),
        runtime_status=[
            OrchestrationRuntimeStatus.Completed,
            OrchestrationRuntimeStatus.Failed,
            OrchestrationRuntimeStatus.Terminated,
        ],
    )
