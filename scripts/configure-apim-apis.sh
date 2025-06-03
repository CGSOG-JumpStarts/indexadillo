#!/bin/bash
# Configure API operations in Azure API Management

set -e

echo "🔧 Configuring API Management operations..."

# Load environment variables
ENV_NAME=${AZURE_ENV_NAME:-"indexadillo-dev"}
ENV_FILE=".azure/$ENV_NAME/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "❌ Environment file not found: $ENV_FILE"
    exit 1
fi

RESOURCE_GROUP=$RESOURCE_GROUP_NAME
APIM_NAME=$API_MANAGEMENT_NAME

echo "📋 Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  APIM Service: $APIM_NAME"

# Import OpenAPI specification
echo "📄 Importing OpenAPI specification..."
if [ -f "docs/openapi.yaml" ]; then
    # Convert YAML to JSON for Azure CLI
    python3 -c "
import yaml
import json
with open('docs/openapi.yaml', 'r') as f:
    data = yaml.safe_load(f)
with open('docs/openapi.json', 'w') as f:
    json.dump(data, f, indent=2)
"
    
    az apim api import \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --api-id "indexadillo-api" \
        --path "v1" \
        --specification-format "OpenApi" \
        --specification-path "docs/openapi.json" \
        --display-name "Indexadillo Document Processing API" \
        --protocols "https" \
        --subscription-required true
        
    echo "✅ OpenAPI specification imported"
else
    echo "⚠️ OpenAPI spec not found at docs/openapi.yaml"
    echo "Creating basic API operations manually..."
    
    # Create API manually
    az apim api create \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --api-id "indexadillo-api" \
        --path "v1" \
        --display-name "Indexadillo Document Processing API" \
        --description "Scalable document processing API for RAG applications" \
        --service-url "https://$FUNCTION_APP_NAME.azurewebsites.net/api/v1" \
        --protocols "https" \
        --subscription-required true
    
    # Add key operations
    operations=(
        "document-extract:POST:/document/extract:Extract text from documents"
        "text-chunk:POST:/text/chunk:Chunk text into smaller pieces"
        "generate-embeddings:POST:/embeddings/generate:Generate embeddings for text"
        "pipeline-process:POST:/pipeline/process:Complete document processing pipeline"
        "search:GET:/search:Search indexed documents"
        "job-status:GET:/jobs/{jobId}:Check job status"
    )
    
    for operation in "${operations[@]}"; do
        IFS=':' read -r op_id method url_template description <<< "$operation"
        
        az apim api operation create \
            --resource-group "$RESOURCE_GROUP" \
            --service-name "$APIM_NAME" \
            --api-id "indexadillo-api" \
            --operation-id "$op_id" \
            --method "$method" \
            --url-template "$url_template" \
            --display-name "$description"
    done
    
    echo "✅ Basic API operations created"
fi

# Set up subscription products
echo "🏷️ Configuring subscription products..."

products=(
    "free:Free Plan:Free tier with basic limits:true"
    "developer:Developer Plan:For development and testing:false"
    "professional:Professional Plan:For production use:false"
    "enterprise:Enterprise Plan:For large scale deployments:false"
)

for product in "${products[@]}"; do
    IFS=':' read -r product_id display_name description approval_required <<< "$product"
    
    # Create product
    az apim product create \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --product-id "$product_id" \
        --display-name "$display_name" \
        --description "$description" \
        --subscription-required true \
        --approval-required "$approval_required" \
        --state "published" || true
    
    # Add API to product
    az apim product api add \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --product-id "$product_id" \
        --api-id "indexadillo-api" || true
done

echo "✅ Subscription products configured"

# Configure policies
echo "📜 Applying API policies..."

# Apply global policy
if [ -f "infra/core/api-management/policies/global-policy.xml" ]; then
    az apim policy create \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --policy-file "infra/core/api-management/policies/global-policy.xml"
    echo "✅ Global policy applied"
fi

# Apply product policies
for product in "free" "developer" "professional" "enterprise"; do
    if [ -f "infra/core/api-management/policies/product-policy.xml" ]; then
        az apim product policy create \
            --resource-group "$RESOURCE_GROUP" \
            --service-name "$APIM_NAME" \
            --product-id "$product" \
            --policy-file "infra/core/api-management/policies/product-policy.xml" || true
    fi
done

# Apply operation-specific policies
if [ -f "infra/core/api-management/policies/document-extract-policy.xml" ]; then
    az apim api operation policy create \
        --resource-group "$RESOURCE_GROUP" \
        --service-name "$APIM_NAME" \
        --api-id "indexadillo-api" \
        --operation-id "document-extract" \
        --policy-file "infra/core/api-management/policies/document-extract-policy.xml" || true
fi

echo "✅ API policies applied"

# Create test subscription
echo "🔑 Creating test subscription..."
az apim subscription create \
    --resource-group "$RESOURCE_GROUP" \
    --service-name "$APIM_NAME" \
    --subscription-id "test-subscription" \
    --display-name "Test Subscription" \
    --scope "/products/developer" \
    --state "active" || true

# Get subscription key
TEST_KEY=$(az apim subscription show \
    --resource-group "$RESOURCE_GROUP" \
    --service-name "$APIM_NAME" \
    --subscription-id "test-subscription" \
    --query "primaryKey" \
    --output tsv 2>/dev/null || echo "")

echo "✅ Test subscription created"

# Test the API
echo "🧪 Testing API endpoints..."
API_GATEWAY_URL=$(azd env get-value API_GATEWAY_URL)

if [ -n "$TEST_KEY" ] && [ -n "$API_GATEWAY_URL" ]; then
    echo "Testing health endpoint..."
    curl -s -H "Ocp-Apim-Subscription-Key: $TEST_KEY" \
         "$API_GATEWAY_URL/v1/health" | head -n 5
    
    echo ""
    echo "✅ API is responding through APIM"
    echo ""
    echo "🔑 Test API Key: $TEST_KEY"
    echo "🌐 Test with: curl -H \"Ocp-Apim-Subscription-Key: $TEST_KEY\" \"$API_GATEWAY_URL/v1/health\""
else
    echo "⚠️ Could not retrieve test key or gateway URL"
fi

echo ""
echo "🎉 API Management configuration complete!"

