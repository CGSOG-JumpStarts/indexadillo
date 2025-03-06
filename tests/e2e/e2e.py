import os
import time
import requests
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
import pathlib
import random
import string

def test_e2e_document_indexing():
    # Retrieve necessary configuration from environment variables.
    source_storage_account = os.environ["SOURCE_STORAGE_ACCOUNT_NAME"]
    container_name = os.environ.get("BLOB_CONTAINER", "source")
    index_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/index"
    status_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/status"
    search_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/search"
    index_name = os.environ.get("TEST_INDEX_NAME", f"test-index-{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}")

    # Upload a sample PDF file to blob storage.
    blob_name = "sample.pdf"
    pdf_path = f"{pathlib.Path(__file__).parent.resolve()}/{blob_name}"  # Ensure this file exists in your repo.
    token_credential = DefaultAzureCredential()

    blob_service_client = BlobServiceClient(
        account_url=f"https://{source_storage_account}.blob.core.windows.net",
        credential=token_credential
    )
    container_client = blob_service_client.get_container_client(container_name)

    with open(pdf_path, "rb") as data:
        container_client.upload_blob(name=blob_name, data=data, overwrite=True)

    # Trigger document indexing via an HTTP call.
    response = requests.post(index_endpoint, json={
            "prefix_list": [""],
            "index_name": index_name
        })
    response.raise_for_status()
    status_id = response.text
    assert status_id, "No statusId returned from the indexing endpoint."

    # Poll the status endpoint until the indexing is finished.
    poll_url = f"{status_endpoint}/{status_id}"
    for _ in range(60):  # adjust the number of retries as needed
        status_resp = requests.get(poll_url)
        status_resp.raise_for_status()
        status = status_resp.json().get('runtimeStatus')
        if status == "Completed":
            break
        time.sleep(5)
    else:
        assert False, "Document indexing did not finish within the expected time."

    # Verify that the document exists in the AI search results.
    search_resp = requests.get(search_endpoint, params={"q": "Elements of Contoso s implementation", "index_name": index_name })
    search_resp.raise_for_status()
    results = search_resp.json()
    assert any(blob_name in doc.get("sourcepages", "").split("#")[0] for doc in results), "Document not found in AI search."

test_e2e_document_indexing()