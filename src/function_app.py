import json
import logging
import os
import azure.functions as func
from azure.durable_functions import DurableOrchestrationClient
from application.app import app
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.models import VectorQuery
from azure.identity import DefaultAzureCredential
from orchestrators.index import index
from activities.listblob import list_blobs_chunk
from activities.cracking import document_cracking
from activities.chuncking import chunking
from activities.embedding import embedding
from activities.search import ensure_index_exists, add_documents


defaults = {
    "BLOB_AMOUNT_PARALLEL": int(os.environ.get("BLOB_AMOUNT_PARALLEL", "20")),
    "SEARCH_INDEX_NAME": os.environ.get("SEARCH_INDEX_NAME", "default-index"),
    "BLOB_CONTAINER_NAME": os.environ.get("BLOB_CONTAINER_NAME", "source")
}


@app.function_name(name='index_event_grid')
@app.event_grid_trigger(arg_name='event')
@app.durable_client_input(client_name="client")
async def index_event_grid(event: func.EventGridEvent, client: DurableOrchestrationClient):
    if event.get_json()["api"] != "PutBlob":
        logging.info("Event type is not BlobCreated. Skipping execution.")
        return
    
    path_in_container = extract_path(event)
    logging.info(f'Python EventGrid trigger processed a BlobCreated event. Path: {path_in_container}')

    instance_id = await client.start_new("index", client_input={"prefix_list": [path_in_container], "defaults": defaults})
    logging.info(f'Started indexing with id: {instance_id}')

def extract_path(event: func.EventGridEvent):
    subject = event.subject
    path_in_container = subject.split("/blobs/", 1)[-1]
    return path_in_container

@app.function_name(name='status')
@app.route(route="status", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def status(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('Retrieving status of all orchestrations.')
    results = await client.get_status_all()
    return func.HttpResponse(json.dumps([result.to_json() for result in results]), status_code=200)

@app.function_name(name='status_id')
@app.route(route="status/{id}", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def status_id(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('Retrieving status of all orchestrations.')
    id = req.route_params.get('id')
    def str_to_bool(value):
        if value is None:
            return False
        return value.lower() in ['true', '1']
    show_history = str_to_bool(req.params.get('show_history')) or False
    show_history_output = str_to_bool(req.params.get('show_history_output')) or False
    show_input = str_to_bool(req.params.get('show_input')) or False
    result = await client.get_status(instance_id=id, show_history=show_history, show_history_output=show_history_output, show_input=show_input)
    result_json = result.to_json()
    if show_history and hasattr(result, 'historyEvents'):
        result_json["historyEvents"] = list(result.historyEvents)
    else:
        result_json["historyEvents"] = None

    return func.HttpResponse(json.dumps(result_json), status_code=200)

@app.function_name(name='index_http')
@app.route(route="index", methods=[func.HttpMethod.POST])
@app.durable_client_input(client_name="client")
async def index_http(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('Kick off indexing process.')
    input = req.get_json()
    instance_id = await client.start_new(
        orchestration_function_name="index",
        client_input={"prefix_list": input['prefix_list'], "index_name": input['index_name'], "defaults": defaults})
    return func.HttpResponse(instance_id, status_code=200)

@app.function_name(name='orchestration_health')
@app.route(route="orchestration_health", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def orchestration_health(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    try:
        # check the status of all orchestrations
        await client.get_status_all()

        return func.HttpResponse("Healthy", status_code=200)
    except Exception as ex:
        logging.error(f"Health check failed: {ex}")
        return func.HttpResponse("Unhealthy", status_code=503)
    
@app.route(route="search", methods=[func.HttpMethod.GET])
async def search_index(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Grab the search query from the URL (e.g., ?q=example)
        query = req.params.get('q')
        if not query:
            return func.HttpResponse(
                "Please provide a search query using the 'q' parameter.", status_code=400
            )
    
        # Get search service configuration from environment variables
        endpoint = os.getenv("SEARCH_SERVICE_ENDPOINT")
        index_name = req.params.get('index_name') or os.environ.get("SEARCH_INDEX_NAME", "default-index")
        if not endpoint or not index_name:
            raise Exception("Missing search service configuration.")

        # Create the async search client
        search_index_client = SearchIndexClient(endpoint=endpoint, credential=DefaultAzureCredential())

        # Execute the search query (using the provided query text)
        search_client = search_index_client.get_search_client(index_name=index_name)
        results = await search_client.search(search_text=query,
                                             query_type="semantic",
                                             select="content, sourcepages, id, storageUrl",
                                             semantic_configuration_name="default")
        docs = []
        async for result in results:
            # Each result has a 'document' property that contains the actual document.
            docs.append(result)

        # Ensure the client is closed properly
        await search_client.close()  
        await search_index_client.close()

        return func.HttpResponse(
            json.dumps(docs), status_code=200, mimetype="application/json"
        )
    except Exception as ex:
        logging.error(f"Search query failed: {ex}")
        return func.HttpResponse("Search failed", status_code=500)

# Add these new HTTP endpoints to function_app.py

@app.function_name(name='api_document_crack')
@app.route(route="api/v1/document/extract", methods=[func.HttpMethod.POST])
async def api_document_crack(req: func.HttpRequest) -> func.HttpResponse:
    """Extract text from document using Document Intelligence"""
    try:
        # Parse request - could be file upload or URL
        content_type = req.headers.get('content-type', '')
        
        if 'multipart/form-data' in content_type:
            # Handle file upload
            files = req.files
            if 'document' not in files:
                return func.HttpResponse("No document provided", status_code=400)
            
            file_data = files['document'].read()
            # Upload to temp blob storage and get URL
            blob_url = await upload_temp_document(file_data, files['document'].filename)
        else:
            # Handle JSON with document URL
            data = req.get_json()
            blob_url = data.get('document_url')
            
        if not blob_url:
            return func.HttpResponse("Document URL required", status_code=400)
            
        # Call document cracking activity
        result = await call_activity_direct("document_cracking", blob_url)
        
        return func.HttpResponse(
            json.dumps({
                "pages": result["pages"],
                "filename": result["filename"],
                "page_count": len(result["pages"]),
                "total_text_length": sum(len(page) for page in result["pages"])
            }),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Document extraction failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Document extraction failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name='api_text_chunk')
@app.route(route="api/v1/text/chunk", methods=[func.HttpMethod.POST])
async def api_text_chunk(req: func.HttpRequest) -> func.HttpResponse:
    """Chunk text into smaller pieces"""
    try:
        data = req.get_json()
        
        # Validate input
        if 'text' not in data:
            return func.HttpResponse("Text content required", status_code=400)
            
        # Prepare document format expected by chunking activity
        document = {
            "pages": [data['text']],
            "filename": data.get('filename', 'user_text.txt'),
            "url": data.get('source_url', '')
        }
        
        # Optional chunking parameters
        chunk_size = data.get('chunk_size', 512)
        chunk_overlap = data.get('chunk_overlap', 128)
        
        # Call chunking activity (would need to modify to accept parameters)
        chunks = await call_activity_direct("chunking", document)
        
        return func.HttpResponse(
            json.dumps({
                "chunks": chunks,
                "chunk_count": len(chunks),
                "total_tokens": sum(chunk['token_count'] for chunk in chunks)
            }),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Text chunking failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Text chunking failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name='api_generate_embeddings')
@app.route(route="api/v1/embeddings/generate", methods=[func.HttpMethod.POST])
async def api_generate_embeddings(req: func.HttpRequest) -> func.HttpResponse:
    """Generate embeddings for text chunks"""
    try:
        data = req.get_json()
        
        if 'texts' not in data:
            return func.HttpResponse("Text array required", status_code=400)
            
        # Prepare chunks format expected by embedding activity
        chunks = []
        for i, text in enumerate(data['texts']):
            chunks.append({
                "text": text,
                "filename": data.get('filename', f'text_{i}.txt'),
                "url": data.get('source_url', ''),
                "start_page": 0,
                "end_page": 0,
                "start_index": 0,
                "end_index": len(text),
                "token_count": len(text.split())  # Rough estimate
            })
        
        # Call embedding activity
        embedded_chunks = await call_activity_direct("embedding", chunks)
        
        return func.HttpResponse(
            json.dumps({
                "embeddings": [
                    {
                        "text": chunk["text"],
                        "embedding": chunk["embedding"],
                        "dimensions": len(chunk["embedding"])
                    }
                    for chunk in embedded_chunks
                ],
                "model": "text-embedding-3-large",
                "total_tokens": sum(chunk['token_count'] for chunk in embedded_chunks)
            }),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Embedding generation failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Embedding generation failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name='api_pipeline_complete')
@app.route(route="api/v1/pipeline/process", methods=[func.HttpMethod.POST])
async def api_pipeline_complete(req: func.HttpRequest) -> func.HttpResponse:
    """Process document through complete pipeline"""
    try:
        # Handle file upload or URL
        content_type = req.headers.get('content-type', '')
        
        if 'multipart/form-data' in content_type:
            files = req.files
            if 'document' not in files:
                return func.HttpResponse("No document provided", status_code=400)
            
            file_data = files['document'].read()
            blob_url = await upload_temp_document(file_data, files['document'].filename)
            index_name = req.form.get('index_name', 'api-default')
        else:
            data = req.get_json()
            blob_url = data.get('document_url')
            index_name = data.get('index_name', 'api-default')
            
        if not blob_url:
            return func.HttpResponse("Document URL required", status_code=400)
            
        # Start the complete pipeline orchestration
        client = df.DurableOrchestrationClient(req)
        instance_id = await client.start_new(
            "index_document",
            client_input={"blob_url": blob_url, "index_name": index_name}
        )
        
        return func.HttpResponse(
            json.dumps({
                "job_id": instance_id,
                "status": "processing",
                "status_url": f"/api/v1/jobs/{instance_id}",
                "estimated_time": "2-5 minutes"
            }),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Pipeline processing failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Pipeline processing failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.function_name(name='api_job_status')
@app.route(route="api/v1/jobs/{job_id}", methods=[func.HttpMethod.GET])
@app.durable_client_input(client_name="client")
async def api_job_status(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Get job status for async operations"""
    try:
        job_id = req.route_params.get('job_id')
        
        status = await client.get_status(instance_id=job_id)
        
        if not status:
            return func.HttpResponse("Job not found", status_code=404)
            
        response_data = {
            "job_id": job_id,
            "status": status.runtime_status.name.lower(),
            "created_time": status.created_time.isoformat() if status.created_time else None,
            "last_updated": status.last_updated_time.isoformat() if status.last_updated_time else None
        }
        
        if status.runtime_status.name == "Completed":
            response_data["result"] = "Document successfully processed and indexed"
        elif status.runtime_status.name == "Failed":
            response_data["error"] = status.output
            
        return func.HttpResponse(
            json.dumps(response_data),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Job status check failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Status check failed", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

# Helper function to call activities directly (you'd need to implement this)
async def call_activity_direct(activity_name: str, input_data):
    """Helper to call activities outside of orchestration context"""
    # This would require setting up a way to call activities directly
    # or using a minimal orchestrator just for the single activity
    client = df.DurableOrchestrationClient()
    instance_id = await client.start_new(
        f"single_{activity_name}",
        client_input=input_data
    )
    
    # Wait for completion (with timeout)
    status = await client.wait_for_completion_or_create_check_status_response(
        instance_id, timeout_in_milliseconds=30000
    )
    
    return status.output

async def upload_temp_document(file_data: bytes, filename: str) -> str:
    """Upload document to temporary storage and return URL"""
    # Implementation would upload to blob storage with SAS token
    # and return the URL for processing
    pass
