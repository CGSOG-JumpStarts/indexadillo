"""Legacy module spelling retained for deployment compatibility."""

from contextlib import nullcontext

from application.app import app
from core.activity import safe_activity
from core.chunking import chunk_document
from core.config import ProcessingProfile
from core.models import cached_artifact, enrich
from core.storage import store


@app.function_name(name="chunking")
@app.activity_trigger(input_name="ref")
@safe_activity
def chunking(ref: dict) -> dict:
    profile = ProcessingProfile.model_validate(ref["profile"])
    storage = store()

    def compute():
        document = storage.read("artifacts", ref["artifact"])
        if document is None:
            raise ValueError("Extraction artifact is missing")
        chunks = chunk_document(document, profile.chunking)
        with storage.service_slot("enrichment") if profile.enrichment.enabled else nullcontext():
            metadata = enrich(document["content"], profile)
        return {"chunks": chunks, "metadata": metadata}

    artifact = cached_artifact(
        ref["tenant_id"], "chunks", [ref["artifact"], profile.fingerprint("chunking", "enrichment")], compute
    )
    return {**ref, "artifact": artifact}
