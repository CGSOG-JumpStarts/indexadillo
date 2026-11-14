"""Explicit live-Azure test. Never collected by the default offline suite."""

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from azd_env import load  # noqa: E402


def eventually(check, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(5)
    raise AssertionError("Expected Azure state was not observed before the deadline")


def main():
    config = load()
    scope = next(iter(json.loads(config["TENANT_SCOPES_JSON"]).values()))
    root = scope["prefix"] + "integration/" + uuid.uuid4().hex + "/"
    index = scope["indexes"][0]
    base = f"https://{config['FUNCTION_APP_NAME']}.azurewebsites.net"
    with (
        DefaultAzureCredential() as credential,
        httpx.Client(timeout=60) as client,
        BlobServiceClient(
            f"https://{config['SOURCE_STORAGE_ACCOUNT_NAME']}.blob.core.windows.net", credential
        ) as blobs,
    ):
        container = blobs.get_container_client("source")

        def headers():
            return {
                "Authorization": f"Bearer {credential.get_token('api://' + config['ENTRA_AUDIENCE'] + '/.default').token}"
            }

        def search(query):
            result = client.get(
                f"{base}/api/search", headers=headers(), params={"q": query, "index_name": index, "top": 50}
            )
            result.raise_for_status()
            return result.json()

        def reindex():
            result = client.post(
                f"{base}/api/index",
                headers=headers(),
                json={"prefix_list": [root], "index_name": index, "reconcile": True},
            )
            assert result.status_code == 202
            url = base + result.json()["statusUrl"]

            def complete():
                response = client.get(url, headers=headers())
                response.raise_for_status()
                state = response.json()
                assert state["runtimeStatus"] not in ("Failed", "Terminated")
                if state["runtimeStatus"] == "Completed":
                    assert state["output"]["failed"] == 0
                    return True
                return False

            eventually(complete)

        names = [root + "a/sample.pdf", root + "b/sample.pdf"]
        data = (Path(__file__).parent / "sample.pdf").read_bytes()
        try:
            assert client.get(f"{base}/api/search", params={"q": "test"}).status_code in (401, 403)
            for name in names:
                container.upload_blob(name, data, overwrite=True)
            reindex()
            eventually(
                lambda: set(names).issubset({doc["sourcefile"] for doc in search("Contoso implementation")})
            )
            denied = client.post(
                f"{base}/api/index", headers=headers(), json={"prefix_list": ["other-tenant/"]}
            )
            assert denied.status_code == 403
            container.delete_blob(names[0], delete_snapshots="include")
            reindex()
            eventually(
                lambda: names[0] not in {doc["sourcefile"] for doc in search("Contoso implementation")}
            )
            assert names[1] in {doc["sourcefile"] for doc in search("Contoso implementation")}
            print(
                "Authenticated upload, full-path identity, hybrid retrieval, tenant isolation and deletion passed"
            )
        finally:
            for name in names:
                blob = container.get_blob_client(name)
                if blob.exists():
                    blob.delete_blob(delete_snapshots="include")


if __name__ == "__main__":
    main()
