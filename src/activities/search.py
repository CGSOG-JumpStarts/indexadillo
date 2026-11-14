from application.app import app
from core.activity import safe_activity
from core.config import ProcessingProfile
from core.lifecycle import publish, record_failure
from core.storage import store


@app.function_name(name="ensure_index_exists")
@app.activity_trigger(input_name="params")
@safe_activity
def ensure_index_exists(params: dict):
    profile = ProcessingProfile.model_validate(params["profile"])
    registry = store().read("registry", f"{params['index_name']}.json")
    if not registry or registry.get("fingerprint") != profile.fingerprint():
        raise ValueError("Provision the versioned index with scripts/manage_search.py before ingestion")


@app.function_name(name="add_documents")
@app.activity_trigger(input_name="ref")
@safe_activity
def add_documents(ref: dict):
    return publish(ref)


@app.function_name(name="record_document_failure")
@app.activity_trigger(input_name="ref")
@safe_activity
def record_document_failure(ref: dict):
    record_failure(ref)
