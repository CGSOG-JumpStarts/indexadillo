import json
import logging
import os
import time
import uuid
import hashlib
from functools import wraps
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import quote

import azure.functions as func
from azure.durable_functions import DurableOrchestrationClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.models import VectorQuery
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.cosmos import CosmosClient
import datetime

from application.app import app
from orchestrators.index import index
from activities.listblob import list_blobs_chunk
from activities.cracking import document_cracking
from activities.chuncking import chunking
from activities.embedding import embedding
from activities.search import ensure_index_exists, add_documents

# Configuration
defaults = {
    "BLOB_AMOUNT_PARALLEL": int(os.environ.get("BLOB_AMOUNT_PARALLEL", "20")),
    "SEARCH_INDEX_NAME": os.environ.get("SEARCH_INDEX_NAME", "default-index"),
    "BLOB_CONTAINER_NAME": os.environ.get("BLOB_CONTAINER_NAME", "source")
}

# Rate limiting storage (in production, use Redis or Cosmos DB)
rate_limit_storage = defaultdict(list)

# ============================================================================
# AUTHENTICATION & MIDDLEWARE
# ============================================================================

class APIAuthManager:
    def __init__(self):
        self.cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
        self.cosmos_key = os.getenv("COSMOS_KEY")
        
        if self.cosmos_endpoint and self.cosmos_key:
            self.cosmos_client = CosmosClient(
                url=self.cosmos_endpoint,
                credential=self.cosmos_key
            )
            try:
                self.database = self.cosmos_client.get_database_client("indexadillo_api")
                self.users_container = self.database.get_container_client("api_users")
            except Exception as e:
                logging.warning(f"Could not connect to Cosmos DB for API auth: {e}")
                self.cosmos_client = None
        else:
            self.cosmos_client = None
        
    async def validate_api_key(self, api_key: str) -> Optional[Dict]:
        """Validate API key and return user info"""
        if not self.cosmos_client:
            # Fallback for local development - accept any key starting with 'dev_'
            if api_key.startswith('dev_'):
                return {
                    'id': 'dev_user',
                    'plan': 'developer',
                    'active': True,
                    'name': 'Development User'
                }
            return None
            
        try:
            query = "SELECT * FROM c WHERE c.api_key = @api_key AND c.active = true"
            items = list(self.users_container.query_items(
                query=query,
                parameters=[{"name": "@api_key", "value": api_key}]
            ))
            
            if items:
                user = items[0]
                # Update last_used timestamp
                user['last_used'] = int(time.time())
                self.users_container.replace_item(user['id'], user)
                return user
            return None
        except Exception as e:
            logging.error(f"API key validation failed: {e}")
            return None

def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    async def decorated_function(req: func.HttpRequest, *args, **kwargs):
        # Get API key from header
        api_key = (req.headers.get('X-API-Key') or 
                  req.headers.get('Authorization', '').replace('Bearer ', ''))
        
        if not api_key:
            return func.HttpResponse(
                json.dumps({
                    "error": "API key required", 
                    "code": "MISSING_API_KEY",
                    "message": "Include your API key in the X-API-Key header"
                }),
                status_code=401,
                mimetype="application/json"
            )
        
        # Validate API key
        auth_manager = APIAuthManager()
        user = await auth_manager.validate_api_key(api_key)
        
        if not user:
            return func.HttpResponse(
                json.dumps({
                    "error": "Invalid API key", 
                    "code": "INVALID_API_KEY",
                    "message": "The provided API key is not valid or has been deactivated"
                }),
                status_code=401,
                mimetype="application/json"
            )
        
        # Add user info to request context
        req.user = user
        
        # Check rate limits
        rate_limit_result = await check_rate_limits(user, req)
        if rate_limit_result:
            return rate_limit_result
            
        return await f(req, *args, **kwargs)
    
    return decorated_function

async def check_rate_limits(user: Dict, req: func.HttpRequest) -> Optional[func.HttpResponse]:
    """Check if user has exceeded rate limits"""
    user_id = user['id']
    plan = user.get('plan', 'free')
    
    # Define rate limits per plan
    limits = {
        'free': {'requests_per_minute': 10, 'requests_per_hour': 100},
        'developer': {'requests_per_minute': 100, 'requests_per_hour': 2000},
        'basic': {'requests_per_minute': 100, 'requests_per_hour': 2000},
        'professional': {'requests_per_minute': 1000, 'requests_per_hour': 50000},
        'enterprise': {'requests_per_minute': 10000, 'requests_per_hour': 500000}
    }
    
    plan_limits = limits.get(plan, limits['free'])
    current_time = int(time.time())
    
    # Clean old entries (older than 1 hour)
    rate_limit_storage[user_id] = [
        timestamp for timestamp in rate_limit_storage[user_id] 
        if current_time - timestamp < 3600
    ]
    
    # Check hourly limit
    hourly_requests = len(rate_limit_storage[user_id])
    if hourly_requests >= plan_limits['requests_per_hour']:
        return func.HttpResponse(
            json.dumps({
                "error": "Hourly rate limit exceeded",
                "code": "RATE_LIMIT_EXCEEDED",
                "limit": plan_limits['requests_per_hour'],
                "window": "hour",
                "retry_after": 3600 - (current_time % 3600)
            }),
            status_code=429,
            mimetype="application/json"
        )
    
    # Check per-minute limit
    recent_requests = [
        timestamp for timestamp in rate_limit_storage[user_id]
        if current_time - timestamp < 60
    ]
    
    if len(recent_requests) >= plan_limits['requests_per_minute']:
        return func.HttpResponse(
            json.dumps({
                "error": "Per-minute rate limit exceeded",
                "code": "RATE_LIMIT_EXCEEDED", 
                "limit": plan_limits['requests_per_minute'],
                "window": "minute",
                "retry_after": 60
            }),
            status_code=429,
            mimetype="application/json"
        )
    
    # Record this request
    rate_limit_storage[user_id].append(current_time)
    
    return None

# Usage tracking for billing
class UsageTracker:
    def __init__(self):
        cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
        cosmos_key = os.getenv("COSMOS_KEY")
        
        if cosmos_endpoint and cosmos_key:
            try:
                self.cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key)
                self.database = self.cosmos_client.get_database_client("indexadillo_api")
                self.usage_container = self.database.get_container_client("api_usage")
            except Exception as e:
                logging.warning(f"Could not connect to Cosmos DB for usage tracking: {e}")
                self.cosmos_client = None
        else:
            self.cosmos_client = None
    
    async def record_usage(self, user_id: str, endpoint: str, tokens_used: int = 0, 
                          pages_processed: int = 0, success: bool = True):
        """Record API usage for billing purposes"""
        if not self.cosmos_client:
            logging.info(f"Usage: {user_id} - {endpoint} - tokens:{tokens_used} - pages:{pages_processed}")
            return
            
        usage_record = {
            "id": f"{user_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
            "user_id": user_id,
            "endpoint": endpoint,
            "timestamp": int(time.time()),
            "tokens_used": tokens_used,
            "pages_processed": pages_processed,
            "success": success,
            "date": datetime.datetime.utcnow().strftime("%Y-%m-%d")
        }
        
        try:
            self.usage_container.create_item(usage_record)
        except Exception as e:
            logging.error(f"Usage tracking failed: {e}")

def track_usage(endpoint_name: str):
    """Decorator to track API usage"""
    def decorator(f):
        @wraps(f)
        async def decorated_function(req: func.HttpRequest, *args, **kwargs):
            start_time = time.time()
            tokens_used = 0
            pages_processed = 0
            success = False
            
            try:
                result = await f(req, *args, **kwargs)
                success = result.status_code < 400
                
                # Extract usage metrics from response if available
                if hasattr(req, 'user') and result.status_code < 400:
                    try:
                        response_data = json.loads(result.get_body().decode())
                        tokens_used = response_data.get('total_tokens', 0)
                        pages_processed = response_data.get('page_count', 0)
                    except:
                        pass
                
                return result
                
            except Exception as e:
                logging.error(f"Endpoint {endpoint_name} failed: {e}")
                raise
            
            finally:
                # Record usage
                if hasattr(req, 'user'):
                    tracker = UsageTracker()
                    await tracker.record_usage(
                        req.user['id'], 
                        endpoint_name, 
                        tokens_used, 
                        pages_processed, 
                        success
                    )
        
        return decorated_function
    return decorator

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def upload_temp_document(file_data: bytes, filename: str) -> str:
    """Upload document to temporary storage and return URL with SAS token"""
    try:
        source_account_name = os.getenv("SOURCE_STORAGE_ACCOUNT_NAME")
        blob_service_client = BlobServiceClient(  
            account_url=f'https://{source_account_name}.blob.core.windows.net/',
            credential=DefaultAzureCredential()
        )
        
        # Use temp container for API uploads
        container_name = "api-temp"
        container_client = blob_service_client.get_container_client(container_name)
        
        # Create container if it doesn't exist
        try:
            await container_client.create_container()
        except:
            pass  # Container already exists
        
        # Generate unique blob name
        blob_name = f"temp_{int(time.time())}_{uuid.uuid4().hex[:8]}_{filename}"
        
        # Upload file
        await container_client.upload_blob(name=blob_name, data=file_data, overwrite=True)
        
        # Generate SAS token
        user_delegation_key = blob_service_client.get_user_delegation_key(
            key_start_time=datetime.datetime.now(datetime.timezone.utc),
            key_expiry_time=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
        )
        
        sas_token = generate_blob_sas(
            account_name=source_account_name,
            container_name=container_name,
            blob_name=blob_name,
            user_delegation_key=user_delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)
        )
        
        return f"https://{source_account_name}.blob.core.windows.net/{container_name}/{quote(blob_name)}?{sas_token}"
        
    except Exception as e:
        logging.error(f"Failed to upload temp document: {e}")
        raise

async def call_activity_direct(client: DurableOrchestrationClient, activity_name: str, input_data):
    """Helper to call activities through a minimal orchestrator"""
    # Create a simple orchestrator just for the single activity
    instance_id = await client.start_new(
        f"single_activity_orchestrator",
        client_input={"activity_name": activity_name, "input_data": input_data}
    )
    
    # Wait for completion with timeout
    timeout_seconds = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        status = await client.get_status(instance_id)
        
        if status.runtime_status.name == "Completed":
            return status.output
        elif status.runtime_status.name == "Failed":
            raise Exception(f"Activity failed: {status.output}")
        
        await asyncio.sleep(2)
    
    raise Exception("Activity timeout")

# ============================================================================
# SINGLE ACTIVITY ORCHESTRATOR
# ============================================================================

@app.function_name(name="single_activity_orchestrator")
@app.orchestration_trigger(context_name="context")
def single_activity_orchestrator(context):
    """Simple orchestrator to call a single activity"""
    input_data = context.get_input()
    activity_name = input_data["activity_name"]
    activity_input = input_data["input_data"]
    
    result = yield context.call_activity(activity_name, activity_input)
    return result

# ============================================================================
# ORIGINAL ENDPOINTS (Event Grid and Management)
# ============================================================================

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
    logging.info('Retrieving status of specific orchestration.')
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

# ============================================================================
# NEW API ENDPOINTS
# ============================================================================

@app.function_name(name='api_document_extract')
@app.route(route="api/v1/document/extract", methods=[func.HttpMethod.POST])
@app.durable_client_input(client_name="client")
@require_api_key
@track_usage("document_extract")
async def api_document_extract(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Extract text from document using Document Intelligence"""
    try:
        # Parse request - could be file upload or URL
        content_type = req.headers.get('content-type', '')
        
        if 'multipart/form-data' in content_type:
            # Handle file upload
            files = req.files
            if 'document' not in files:
                return func.HttpResponse(
                    json.dumps({"error": "No document provided", "code": "MISSING_DOCUMENT"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            file_data = files['document'].read()
            filename = files['document'].filename
            
            # Check file size limits based on plan
            plan = req.user.get('plan', 'free')
            size_limits = {
                'free': 5 * 1024 * 1024,      # 5MB
                'developer': 25 * 1024 * 1024,  # 25MB
                'basic': 25 * 1024 * 1024,    # 25MB
                'professional': 100 * 1024 * 1024,  # 100MB
                'enterprise': 500 * 1024 * 1024   # 500MB
            }
            
            if len(file_data) > size_limits.get(plan, size_limits['free']):
                return func.HttpResponse(
                    json.dumps({
                        "error": "File size exceeds plan limit",
                        "code": "FILE_TOO_LARGE",
                        "max_size": f"{size_limits.get(plan, size_limits['free']) // (1024*1024)}MB",
                        "plan": plan
                    }),
                    status_code=413,
                    mimetype="application/json"
                )
            
            # Upload to temp blob storage and get URL
            blob_url = await upload_temp_document(file_data, filename)
        else:
            # Handle JSON with document URL
            try:
                data = req.get_json()
                blob_url = data.get('document_url')
                filename = data.get('filename', 'document')
            except:
                return func.HttpResponse(
                    json.dumps({"error": "Invalid JSON", "code": "INVALID_JSON"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
        if not blob_url:
            return func.HttpResponse(
                json.dumps({"error": "Document URL required", "code": "MISSING_URL"}),
                status_code=400,
                mimetype="application/json"
            )
            
        # Call document cracking activity
        result = await call_activity_direct(client, "document_cracking", blob_url)
        
        return func.HttpResponse(
            json.dumps({
                "pages": result["pages"],
                "filename": result["filename"],
                "page_count": len(result["pages"]),
                "total_text_length": sum(len(page) for page in result["pages"]),
                "processing_time_ms": 0  # Would need to track this
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
@app.durable_client_input(client_name="client")
@require_api_key
@track_usage("text_chunk")
async def api_text_chunk(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Chunk text into smaller pieces"""
    try:
        data = req.get_json()
        
        # Validate input
        if 'text' not in data:
            return func.HttpResponse(
                json.dumps({"error": "Text content required", "code": "MISSING_TEXT"}),
                status_code=400,
                mimetype="application/json"
            )
            
        # Prepare document format expected by chunking activity
        document = {
            "pages": [data['text']],
            "filename": data.get('filename', 'user_text.txt'),
            "url": data.get('source_url', '')
        }
        
        # Call chunking activity
        chunks = await call_activity_direct(client, "chunking", document)
        
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
@app.durable_client_input(client_name="client")
@require_api_key
@track_usage("generate_embeddings")
async def api_generate_embeddings(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Generate embeddings for text chunks"""
    try:
        data = req.get_json()
        
        if 'texts' not in data:
            return func.HttpResponse(
                json.dumps({"error": "Text array required", "code": "MISSING_TEXTS"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Check batch size limits
        if len(data['texts']) > 100:
            return func.HttpResponse(
                json.dumps({"error": "Maximum 100 texts per request", "code": "BATCH_TOO_LARGE"}),
                status_code=400,
                mimetype="application/json"
            )
            
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
        embedded_chunks = await call_activity_direct(client, "embedding", chunks)
        
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
@app.durable_client_input(client_name="client")
@require_api_key
@track_usage("pipeline_complete")
async def api_pipeline_complete(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Process document through complete pipeline"""
    try:
        # Handle file upload or URL
        content_type = req.headers.get('content-type', '')
        
        if 'multipart/form-data' in content_type:
            files = req.files
            if 'document' not in files:
                return func.HttpResponse(
                    json.dumps({"error": "No document provided", "code": "MISSING_DOCUMENT"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            file_data = files['document'].read()
            blob_url = await upload_temp_document(file_data, files['document'].filename)
            index_name = req.form.get('index_name', f"api-{req.user['id']}")
        else:
            data = req.get_json()
            blob_url = data.get('document_url')
            index_name = data.get('index_name', f"api-{req.user['id']}")
            
        if not blob_url:
            return func.HttpResponse(
                json.dumps({"error": "Document URL required", "code": "MISSING_URL"}),
                status_code=400,
                mimetype="application/json"
            )
            
        # Start the complete pipeline orchestration
        instance_id = await client.start_new(
            "index_document",
            client_input={"blob_url": blob_url, "index_name": index_name}
        )
        
        return func.HttpResponse(
            json.dumps({
                "job_id": instance_id,
                "status": "processing",
                "status_url": f"/api/v1/jobs/{instance_id}",
                "estimated_time": "2-5 minutes",
                "index_name": index_name
            }),
            status_code=202,
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
@require_api_key
async def api_job_status(req: func.HttpRequest, client: DurableOrchestrationClient) -> func.HttpResponse:
    """Get job status for async operations"""
    try:
        job_id = req.route_params.get('job_id')
        
        status = await client.get_status(instance_id=job_id)
        
        if not status:
            return func.HttpResponse(
                json.dumps({"error": "Job not found", "code": "JOB_NOT_FOUND"}),
                status_code=404,
                mimetype="application/json"
            )
            
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

@app.function_name(name='api_search')
@app.route(route="api/v1/search", methods=[func.HttpMethod.GET])
@require_api_key
@track_usage("search")
async def api_search(req: func.HttpRequest) -> func.HttpResponse:
    """Search documents with authentication"""
    try:
        query = req.params.get('q')
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Search query required", "code": "MISSING_QUERY"}),
                status_code=400,
                mimetype="application/json"
            )
    
        endpoint = os.getenv("SEARCH_SERVICE_ENDPOINT")
        index_name = req.params.get('index_name') or f"api-{req.user['id']}"
        
        if not endpoint:
            raise Exception("Missing search service configuration.")

        search_index_client = SearchIndexClient(endpoint=endpoint, credential=DefaultAzureCredential())
        search_client = search_index_client.get_search_client(index_name=index_name)
        
        results = await search_client.search(
            search_text=query,
            query_type="semantic",
            select="content, sourcepages, id, storageUrl",
            semantic_configuration_name="default",
            top=int(req.params.get('top', 10))
        )
        
        docs = []
        async for result in results:
            docs.append(result)

        await search_client.close()  
        await search_index_client.close()

        return func.HttpResponse(
            json.dumps({
                "results": docs,
                "query": query,
                "index_name": index_name,
                "total_results": len(docs)
            }),
            mimetype="application/json"
        )
        
    except Exception as ex:
        logging.error(f"Search query failed: {ex}")
        return func.HttpResponse(
            json.dumps({"error": "Search failed", "details": str(ex)}),
            status_code=500,
            mimetype="application/json"
        )

# ============================================================================
# API INFORMATION ENDPOINTS
# ============================================================================

@app.function_name(name='api_info')
@app.route(route="api/v1/info", methods=[func.HttpMethod.GET])
async def api_info(req: func.HttpRequest) -> func.HttpResponse:
    """Get API information and status"""
    return func.HttpResponse(
        json.dumps({
            "name": "Indexadillo Document Processing API",
            "version": "1.0.0",
            "description": "Scalable document processing API for RAG applications",
            "endpoints": {
                "document_extract": "/api/v1/document/extract",
                "text_chunk": "/api/v1/text/chunk", 
                "generate_embeddings": "/api/v1/embeddings/generate",
                "pipeline_process": "/api/v1/pipeline/process",
                "search": "/api/v1/search",
                "job_status": "/api/v1/jobs/{job_id}"
            },
            "documentation": "https://docs.indexadillo.ai",
            "support": "support@indexadillo.ai"
        }),
        mimetype="application/json"
    )

@app.function_name(name='api_health')
@app.route(route="api/v1/health", methods=[func.HttpMethod.GET])
async def api_health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    try:
        # Test key services
        endpoint = os.getenv("SEARCH_SERVICE_ENDPOINT")
        openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        di_endpoint = os.getenv("DI_ENDPOINT")
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "services": {
                "search": bool(endpoint),
                "openai": bool(openai_endpoint), 
                "document_intelligence": bool(di_endpoint),
                "storage": bool(os.getenv("SOURCE_STORAGE_ACCOUNT_NAME"))
            }
        }
        
        # Check if any critical services are missing
        if not all(health_status["services"].values()):
            health_status["status"] = "degraded"
            
        return func.HttpResponse(
            json.dumps(health_status),
            status_code=200 if health_status["status"] == "healthy" else 503,
            mimetype="application/json"
        )
        
    except Exception as e:
        return func.HttpResponse(
            json.dumps({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.datetime.utcnow().isoformat()
            }),
            status_code=503,
            mimetype="application/json"
        )
