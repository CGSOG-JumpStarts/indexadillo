from azure.durable_functions import DurableOrchestrationContext, RetryOptions

from application.app import app


@app.function_name(name="index")
@app.orchestration_trigger(context_name="context")
def index(context: DurableOrchestrationContext):
    job = context.get_input()
    retry = RetryOptions(30000, 10)
    yield context.call_activity_with_retry("ensure_index_exists", retry, job)
    totals = job.get("totals", {"published": 0, "unchanged": 0, "superseded": 0, "deleted": 0, "failed": 0})
    phase = job.get("phase", "sources")
    for _ in range(25):
        activity = "list_blobs_chunk" if phase == "sources" else "list_missing_documents"
        page = yield context.call_activity_with_retry(
            activity,
            retry,
            {
                "job": job,
                "offset": job.get("offset", 0),
                "token": job.get("token"),
            },
        )
        tasks = [context.call_sub_orchestrator("index_document", doc) for doc in page["documents"]]
        outcomes = (yield context.task_all(tasks)) if tasks else []
        for result in outcomes:
            totals[result["status"]] += 1
        job = {**job, "totals": totals, "offset": page.get("offset", 0), "token": page["token"]}
        context.set_custom_status({"tenant_id": job["scope"]["tenant_id"], "phase": phase, "totals": totals})
        if page["done"]:
            if phase == "sources" and job.get("reconcile", False):
                phase = "missing"
                job.update(phase=phase, token=None, offset=0)
            else:
                return totals
    context.continue_as_new({**job, "phase": phase})


@app.function_name(name="index_document")
@app.orchestration_trigger(context_name="context")
def index_document(context: DurableOrchestrationContext):
    ref = context.get_input()
    retry = RetryOptions(30000, 10)
    stage = "ensure_index_exists"
    try:
        yield context.call_activity_with_retry("ensure_index_exists", retry, ref)
        if ref.get("operation") != "delete":
            for activity in ("document_cracking", "chunking", "embedding"):
                stage = activity
                ref = yield context.call_activity_with_retry(activity, retry, ref)
                if ref.get("superseded"):
                    return {"status": "superseded"}
        stage = "add_documents"
        return (yield context.call_activity_with_retry("add_documents", retry, ref))
    except Exception:
        yield context.call_activity_with_retry(
            "record_document_failure", retry, {**ref, "failed_stage": stage}
        )
        return {"status": "failed"}
