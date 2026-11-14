from application.app import app
from core.activity import safe_activity
from core.config import ProcessingProfile
from core.models import cached_artifact, embed, embedding_batches
from core.storage import store


@app.function_name(name="embedding")
@app.activity_trigger(input_name="ref")
@safe_activity
def embedding(ref: dict) -> dict:
    profile = ProcessingProfile.model_validate(ref["profile"])
    storage = store()

    def compute():
        document = storage.read("artifacts", ref["artifact"])
        if document is None:
            raise ValueError("Chunk artifact is missing")
        chunks = document["chunks"]
        vectors = []
        texts = [chunk.get("context", "") + "\n" + chunk["text"] for chunk in chunks]
        for batch in embedding_batches(texts, profile.embedding, profile.chunking.encoding):

            def compute_batch(batch=batch):
                with storage.service_slot("embedding"):
                    return {"vectors": embed(batch, profile)}

            name = cached_artifact(
                ref["tenant_id"],
                "embedding-batches",
                [profile.fingerprint("embedding"), batch],
                compute_batch,
            )
            vectors.extend(storage.read("artifacts", name)["vectors"])
        return {
            **document,
            "chunks": [{**chunk, "embedding": vector} for chunk, vector in zip(chunks, vectors, strict=True)],
        }

    artifact = cached_artifact(
        ref["tenant_id"], "embeddings", [ref["artifact"], profile.fingerprint("embedding")], compute
    )
    return {**ref, "artifact": artifact}
