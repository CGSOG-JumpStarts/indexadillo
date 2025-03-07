import os
import time
import requests
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, AzureDeveloperCliCredential
import pathlib
import random
import string

def test_e2e_document_indexing():
    print("Starting end-to-end document indexing test...")

    # Retrieve necessary configuration from environment variables.
    source_storage_account = os.environ["SOURCE_STORAGE_ACCOUNT_NAME"]
    container_name = os.environ.get("BLOB_CONTAINER", "source")
    index_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/index"
    status_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/status"
    search_endpoint = f"https://{os.environ['FUNCTION_APP_NAME']}.azurewebsites.net/api/search"
    index_name = os.environ.get("TEST_INDEX_NAME", f"test-index-{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}")

    print(f"Using index name: {index_name}")

    # Upload a sample PDF file to blob storage.
    blob_name = "sample.pdf"
    pdf_path = f"{pathlib.Path(__file__).parent.resolve()}/{blob_name}"  # Ensure this file exists in your repo.


    with open(pdf_path, "rb") as file:
        file_content = file.read()

    for attempt in range(30):
        try:
            print(f"Connecting to Azure Blob Storage: {source_storage_account}")
            token_credential = DefaultAzureCredential()

            blob_service_client = BlobServiceClient(
                account_url=f"https://{source_storage_account}.blob.core.windows.net",
                credential=token_credential
            )
            container_client = blob_service_client.get_container_client(container_name)

            print(f"Uploading file {blob_name} to container {container_name}...")
            container_client.upload_blob(name=blob_name, data=file_content, read_timeout=120, overwrite=True)
            print("File uploaded successfully.")
            break
        except Exception as e:
            print(f"Upload attempt {attempt+1} failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
    else:
        print("ERROR: Document upload was not possible.")
        assert False, "Document upload was not possible."
    # Trigger document indexing via an HTTP call.
    print("Triggering document indexing...")
    response = requests.post(index_endpoint, json={
            "prefix_list": [""],
            "index_name": index_name
        })
    response.raise_for_status()
    status_id = response.text
    assert status_id, "No statusId returned from the indexing endpoint."
    print(f"Indexing started, received status ID: {status_id}")

    # Poll the status endpoint until the indexing is finished.
    poll_url = f"{status_endpoint}/{status_id}"
    print("Polling indexing status...")
    for attempt in range(60):  # adjust the number of retries as needed
        status_resp = requests.get(poll_url)
        status_resp.raise_for_status()
        status = status_resp.json().get('runtimeStatus')
        print(f"Status check {attempt+1}: {status}")
        if status not in ["Pending", "Running", "Completed"]:
            print(f"ERROR: Document indexing did not finish. Reason: {status_resp.json()}")
            assert False, "Document indexing did not finish."
        if status == "Completed":
            print("Indexing completed successfully.")
            break
        time.sleep(5)
    else:
        print("ERROR: Document indexing did not finish within the expected time.")
        assert False, "Document indexing did not finish within the expected time."

    # Verify that the document exists in the AI search results.
    print("Verifying document existence in AI search...")
    search_resp = requests.get(search_endpoint, params={"q": "Elements of Contoso s implementation", "index_name": index_name})
    search_resp.raise_for_status()
    results = search_resp.json()
    found = any(blob_name in doc.get("sourcepages", "").split("#")[0] for doc in results)

    if found:
        print("Document successfully found in AI search.")
    else:
        print("ERROR: Document not found in AI search.")
        assert False, "Document not found in AI search."

    print("End-to-end document indexing test completed successfully.")

test_e2e_document_indexing()
