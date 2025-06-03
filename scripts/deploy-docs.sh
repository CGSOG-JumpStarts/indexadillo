# Deploy script for Azure Static Web Apps
#!/bin/bash

set -e

echo "🚀 Deploying API Documentation to Azure Static Web Apps..."

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is required but not installed"
    exit 1
fi

# Check if logged in to Azure
if ! az account show &> /dev/null; then
    echo "❌ Please log in to Azure CLI first: az login"
    exit 1
fi

# Load environment variables
ENV_FILE=".azure/${AZURE_ENV_NAME:-indexadillo-dev}/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ Loaded environment variables from $ENV_FILE"
else
    echo "❌ Environment file not found: $ENV_FILE"
    echo "Run 'azd env get-values' to create it"
    exit 1
fi

# Set variables
RESOURCE_GROUP=${RESOURCE_GROUP_NAME:-"rg-${AZURE_ENV_NAME}"}
STATIC_WEB_APP_NAME="swa-docs-${AZURE_ENV_NAME}"
LOCATION=${AZURE_LOCATION:-"East US 2"}

echo "📋 Configuration:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Static Web App: $STATIC_WEB_APP_NAME"
echo "  Location: $LOCATION"

# Create static web app if it doesn't exist
echo "🏗️ Creating Static Web App..."

if ! az staticwebapp show --name "$STATIC_WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null; then
    az staticwebapp create \
        --name "$STATIC_WEB_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku "Free" \
        --source "https://github.com/your-username/indexadillo" \
        --branch "main" \
        --app-location "/docs" \
        --output-location "" \
        --login-with-github
    
    echo "✅ Static Web App created successfully"
else
    echo "ℹ️ Static Web App already exists"
fi

# Get the deployment token
echo "🔑 Getting deployment token..."
DEPLOYMENT_TOKEN=$(az staticwebapp secrets list \
    --name "$STATIC_WEB_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.apiKey" \
    --output tsv)

if [ -z "$DEPLOYMENT_TOKEN" ]; then
    echo "❌ Failed to get deployment token"
    exit 1
fi

# Deploy the static content
echo "📦 Deploying static content..."

# Install Azure Static Web Apps CLI if not present
if ! command -v swa &> /dev/null; then
    echo "📥 Installing Azure Static Web Apps CLI..."
    npm install -g @azure/static-web-apps-cli
fi

# Deploy using SWA CLI
cd docs
swa deploy \
    --deployment-token "$DEPLOYMENT_TOKEN" \
    --app-location "." \
    --output-location "." \
    --env "production"

cd ..

# Get the URL
APP_URL=$(az staticwebapp show \
    --name "$STATIC_WEB_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "defaultHostname" \
    --output tsv)

echo ""
echo "🎉 Documentation deployed successfully!"
echo "📖 Documentation URL: https://$APP_URL"
echo "⚙️ Manage at: https://portal.azure.com/#resource/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/staticSites/$STATIC_WEB_APP_NAME"
echo ""
echo "Next steps:"
echo "1. Set up custom domain: docs.indexadillo.ai"
echo "2. Configure GitHub Actions for automatic deployment"
echo "3. Add SSL certificate for custom domain"
echo ""

# Update azd environment with documentation URL
azd env set DOCS_URL "https://$APP_URL"

echo "✅ Deployment complete!"
