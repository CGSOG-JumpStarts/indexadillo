from application.app import app
from core.activity import safe_activity
from core.config import ProcessingProfile
from core.models import cached_artifact, extract
from core.storage import Superseded, digest, store


@app.function_name(name="document_cracking")
@app.activity_trigger(input_name="ref")
@safe_activity
def document_cracking(ref: dict) -> dict:
    if ref["visibility"] not in ("restricted", "tenant") or (
        ref["visibility"] == "restricted" and not ref["allowed_groups"]
    ):
        raise ValueError("Restricted documents need explicit allowed groups")
    profile = ProcessingProfile.model_validate(ref["profile"])
    storage = store()
    try:
        props = storage.assert_current(ref)
        data = storage.source_bytes(ref, profile.extraction.max_bytes)
    except Superseded:
        return {**ref, "superseded": True}

    def compute():
        with storage.service_slot("extraction"):
            return extract(data, profile.extraction, props.content_settings.content_type or "application/pdf")

    artifact = cached_artifact(
        ref["tenant_id"], "extraction", [digest(data), profile.fingerprint("extraction")], compute
    )
    return {**ref, "artifact": artifact}
