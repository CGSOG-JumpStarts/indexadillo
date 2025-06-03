#!/bin/bash
# Script to populate local.settings.json from Azure deployment

set -e

echo "Setting up local development environment..."

# Check if azd is available
if ! command -v azd &> /dev/null; then
    echo "Error: azd is required but not installed"
    exit 1
fi

# Load environment variables from azd
echo "Loading environment variables from azd..."
ENV_OUTPUT=$(azd env get-values)

if [ $? -ne 0 ]; then
    echo "Error: Failed to get azd environment variables"
    echo "Make sure you've run 'azd up' first"
    exit 1
fi

# Parse environment variables
while IFS='=' read -r key value; do
    # Remove quotes from value
    value=$(echo "$value" | sed 's/^"//' | sed 's/"$//')
    export "$key=$value"
done <<< "$ENV_OUTPUT"

echo "Found environment: $AZURE_ENV_NAME"

# Get additional values from Azure CLI
echo "Getting additional Azure information..."

# Get Application Insights instrumentation key
APPINSIGHTS_KEY=$(az monitor app-insights component show \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --app "$RESOURCE_GROUP_NAME" \
    --query "instrumentationKey" \
    --output tsv 2>/dev/null || echo "")

# Get managed identity client ID from the function app
MANAGED_IDENTITY_CLIENT_ID=$(az functionapp identity show \
    --name "$FUNCTION_APP_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --query "userAssignedIdentities.*.clientId" \
    --output tsv 2>/dev/null || echo "")

# Get Cosmos DB info if it exists
COSMOS_ENDPOINT=$(az cosmosdb show \
    --name "cosmos-${AZURE_ENV_NAME}" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --query "documentEndpoint" \
    --output tsv 2>/dev/null || echo "")

COSMOS_KEY=$(az cosmosdb keys list \
    --name "cosmos-${AZURE_ENV_NAME}" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --query "primaryMasterKey" \
    --output tsv 2>/dev/null || echo "")

# Create local.settings.json
echo "Creating src/local.settings.json..."

cat > src/local.settings.json << EOF
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
    
    "SOURCE_STORAGE_ACCOUNT_NAME": "${SOURCE_STORAGE_ACCOUNT_NAME}",
    "DI_ENDPOINT": "${DI_ENDPOINT}",
    "AZURE_OPENAI_ENDPOINT": "${AZURE_OPENAI_ENDPOINT}",
    "SEARCH_SERVICE_ENDPOINT": "${SEARCH_SERVICE_ENDPOINT}",
    
    "AZURE_CLIENT_ID": "${MANAGED_IDENTITY_CLIENT_ID}",
    "APPINSIGHTS_INSTRUMENTATIONKEY": "${APPINSIGHTS_KEY}",
    
    "BLOB_AMOUNT_PARALLEL": "20",
    "SEARCH_INDEX_NAME": "default-index",
    "BLOB_CONTAINER_NAME": "source"$(if [ -n "$COSMOS_ENDPOINT" ]; then echo ",
    
    \"COSMOS_ENDPOINT\": \"${COSMOS_ENDPOINT}\",
    \"COSMOS_KEY\": \"${COSMOS_KEY}\""; fi)
  }
}
EOF

echo "✅ Successfully created src/local.settings.json"
echo ""
echo "Next steps:"
echo "1. Start Azurite: Use VS Code command palette -> 'Azurite: Start'"
echo "2. Run the function app: Press F5 in VS Code or use 'func start' in src/ directory"
echo ""
echo "Variables loaded:"
echo "  Storage Account: ${SOURCE_STORAGE_ACCOUNT_NAME}"
echo "  Function App: ${FUNCTION_APP_NAME}"
echo "  Resource Group: ${RESOURCE_GROUP_NAME}"
if [ -n "$COSMOS_ENDPOINT" ]; then
    echo "  Cosmos DB: Configured ✅"
else
    echo "  Cosmos DB: Not found (API features will use dev mode)"
fi
