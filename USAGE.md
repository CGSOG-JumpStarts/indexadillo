## Core Architecture & Components

### **What Indexadillo Does**
Indexadillo automates the entire document processing pipeline:
1. **Document Ingestion** → Upload PDFs/documents to blob storage
2. **Text Extraction** → Uses Azure Document Intelligence to extract text
3. **Chunking** → Breaks documents into smaller, searchable pieces
4. **Embedding** → Creates vector embeddings using OpenAI
5. **Indexing** → Stores everything in Azure AI Search for fast retrieval

### **Key Technologies Used**
- **Azure Durable Functions** (Python) - Orchestrates the workflow with built-in retry logic
- **Azure Document Intelligence** - Extracts text from PDFs and other documents  
- **Azure OpenAI** - Generates text embeddings for semantic search
- **Azure AI Search** - Stores and queries the indexed content
- **Event Grid** - Automatically triggers processing when files are uploaded
- **"Chonkie" Library** - Intelligent document chunking

## Architecture Breakdown

### **Infrastructure Components** (`/infra`)
The Bicep templates deploy these Azure resources:
- **Storage Account** with 'source' container for document uploads
- **Function App** running on Flex Consumption plan
- **Document Intelligence** service for text extraction
- **OpenAI** service for embeddings (text-embedding-3-large model)
- **AI Search** service with vector search capabilities
- **Event Grid** for blob storage event handling
- **Application Insights** for monitoring and telemetry

### **Application Logic** (`/src`)

**Activities** (individual processing steps):
- `cracking.py` - Extracts text from documents using Document Intelligence
- `chunking.py` - Splits documents into manageable chunks with metadata
- `embedding.py` - Generates vector embeddings using OpenAI
- `search.py` - Manages search index creation and document uploads
- `listblob.py` - Handles blob storage operations with pagination

**Orchestrators** (workflow coordination):
- `index.py` - Main orchestrator that coordinates document processing
- Sub-orchestrators for individual document processing with retry logic

**HTTP Endpoints**:
- `POST /api/index` - Manually trigger indexing with custom parameters
- `GET /api/search` - Query the search index
- `GET /api/status` - Monitor processing status
- Event Grid webhook for automatic processing

## How to Incorporate Into Existing Applications

### **Scenario 1: Adding Document Search to Existing App**

If you have an existing web application and want to add document search capabilities:

```python
# In your existing application, call Indexadillo's search endpoint
import requests

def search_documents(query: str, index_name: str = "default-index"):
    response = requests.get(
        f"https://{FUNCTION_APP_NAME}.azurewebsites.net/api/search",
        params={"q": query, "index_name": index_name}
    )
    return response.json()

# Usage in your app
results = search_documents("contract terms")
for result in results:
    print(f"Found in: {result['sourcepages']}")
    print(f"Content: {result['content']}")
```

### **Scenario 2: Integrating with Your Document Management System**

You can programmatically trigger indexing when documents are uploaded to your system:

```python
# Trigger indexing for specific document prefixes
def index_new_documents(document_prefix: str, custom_index: str):
    response = requests.post(
        f"https://{FUNCTION_APP_NAME}.azurewebsites.net/api/index",
        json={
            "prefix_list": [document_prefix],
            "index_name": custom_index
        }
    )
    return response.text  # Returns status ID for monitoring

# Usage
status_id = index_new_documents("contracts/2024/", "contracts-index")
```

### **Scenario 3: Custom Document Processing Pipeline**

You can extend the existing activities or add new ones:

```python
# Add custom activity for your specific document type
@app.function_name(name="custom_processing")
@app.activity_trigger(input_name="document")
def custom_processing(document: Dict) -> Dict:
    # Your custom logic here
    # e.g., extract specific metadata, apply custom filters
    processed_doc = apply_custom_business_logic(document)
    return processed_doc

# Modify the orchestrator to include your custom step
def index_document_custom(context: DurableOrchestrationContext):
    input = context.get_input()
    document = yield context.call_activity("document_cracking", input["blob_url"])
    
    # Add your custom processing step
    document = yield context.call_activity("custom_processing", document)
    
    chunks = yield context.call_activity("chunking", document)
    # ... rest of pipeline
```

### **Scenario 4: Multi-Tenant Document Indexing**

For SaaS applications, you can create separate indexes per tenant:

```python
# Create tenant-specific indexes
def index_tenant_documents(tenant_id: str, document_prefix: str):
    index_name = f"tenant-{tenant_id}-docs"
    return requests.post(
        f"https://{FUNCTION_APP_NAME}.azurewebsites.net/api/index",
        json={
            "prefix_list": [f"tenants/{tenant_id}/{document_prefix}"],
            "index_name": index_name
        }
    )

# Search within tenant scope
def search_tenant_documents(tenant_id: str, query: str):
    index_name = f"tenant-{tenant_id}-docs"
    return search_documents(query, index_name)
```

## Integration Patterns

### **1. Event-Driven Integration**
- Use Event Grid to trigger processing automatically when documents are uploaded
- Set up custom event subscriptions for your application events

### **2. API Integration**
- Call Indexadillo's REST endpoints from your existing application
- Monitor processing status and handle results

### **3. Shared Storage Integration**
- Upload documents to the same blob storage containers
- Use prefix-based organization for different document types

### **4. Custom Activity Extensions**
- Add new activities for specialized document processing
- Integrate with your existing business logic and databases

## Deployment & Configuration

### **Quick Deployment**
```bash
# Clone and deploy
git clone <repository-url>
cd indexadillo
azd env new my-indexadillo
azd auth login
azd up
```

### **Environment Configuration**
Key environment variables you'll need:
- `SOURCE_STORAGE_ACCOUNT_NAME` - Where documents are stored
- `SEARCH_SERVICE_ENDPOINT` - Azure AI Search endpoint
- `AZURE_OPENAI_ENDPOINT` - OpenAI service endpoint
- `DI_ENDPOINT` - Document Intelligence endpoint

### **Custom Configuration**
You can modify `defaults` in `function_app.py`:
```python
defaults = {
    "BLOB_AMOUNT_PARALLEL": 20,  # Parallel processing limit
    "SEARCH_INDEX_NAME": "my-custom-index",
    "BLOB_CONTAINER_NAME": "documents"
}
```

## Benefits for Existing Applications

1. **Scalability** - Durable Functions handle retries and scale automatically
2. **Observability** - Built-in monitoring with Application Insights
3. **Flexibility** - Modular activities can be customized or extended
4. **Cost-Effective** - Serverless architecture only charges for usage
5. **Production-Ready** - Includes proper error handling, retry logic, and testing

This solution is particularly valuable for applications that need to make large document collections searchable, whether for customer support, legal document review, knowledge management, or any RAG-based AI application.
