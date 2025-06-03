#!/bin/bash
# scripts/deploy-apim.sh
# Deploy Azure API Management for Indexadillo

set -e

echo "🚀 Deploying Azure API Management for Indexadillo..."

# Check prerequisites
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is required but not installed"
    exit 1
fi

if ! command -v azd &> /dev/null; then
    echo "❌ Azure Developer CLI (azd) is required but not installed"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo "❌ Please log in to Azure CLI first: az login"
    exit 1
fi

# Load environment variables
ENV_NAME=${AZURE_ENV_NAME:-"indexadillo-dev"}
ENV_FILE=".azure/$ENV_NAME/.env"

if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ Loaded environment variables from $ENV_FILE"
else
    echo "❌ Environment file not found: $ENV_FILE"
    echo "Run 'azd env get-values' first or deploy the base infrastructure"
    exit 1
fi

# Configuration
APIM_TIER=${1:-"Developer"}
PUBLISHER_EMAIL=${2:-"admin@indexadillo.ai"}
PUBLISHER_NAME=${3:-"Indexadillo"}
CUSTOM_DOMAIN=${4:-""}

echo "📋 APIM Configuration:"
echo "  Environment: $ENV_NAME"
echo "  Tier: $APIM_TIER"
echo "  Publisher Email: $PUBLISHER_EMAIL"
echo "  Publisher Name: $PUBLISHER_NAME"
echo "  Custom Domain: ${CUSTOM_DOMAIN:-"(none)"}"
echo ""

# Confirm deployment
read -p "🤔 Deploy API Management with these settings? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

# Update azd environment with APIM settings
echo "⚙️ Updating azd environment..."
azd env set ENABLE_API_MANAGEMENT true
azd env set API_MANAGEMENT_TIER "$APIM_TIER"
azd env set PUBLISHER_EMAIL "$PUBLISHER_EMAIL"
azd env set PUBLISHER_NAME "$PUBLISHER_NAME"

if [ -n "$CUSTOM_DOMAIN" ]; then
    azd env set CUSTOM_DOMAIN_NAME "$CUSTOM_DOMAIN"
fi

# Deploy infrastructure with APIM enabled
echo "🏗️ Deploying infrastructure with API Management..."

# Use the updated main template
cp infra/main.bicep infra/main-backup.bicep
cp infra/main-with-apim.bicep infra/main.bicep

# Update parameters
cat > infra/main.parameters.json << EOF
{
    "\$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {
        "environmentName": {
            "value": "\${AZURE_ENV_NAME}"
        },
        "location": {
            "value": "\${AZURE_LOCATION}"
        },
        "enableApiManagement": {
            "value": true
        },
        "apiManagementTier": {
            "value": "$APIM_TIER"
        },
        "publisherEmail": {
            "value": "$PUBLISHER_EMAIL"
        },
        "publisherName": {
            "value": "$PUBLISHER_NAME"
        },
        "customDomainName": {
            "value": "$CUSTOM_DOMAIN"
        }
    }
}
EOF

# Deploy with azd
echo "📦 Running azd provision..."
azd provision --no-prompt

# Restore original main template
mv infra/main-backup.bicep infra/main.bicep

# Get deployment outputs
echo "📊 Getting deployment information..."
API_GATEWAY_URL=$(azd env get-value API_GATEWAY_URL)
DEVELOPER_PORTAL_URL=$(azd env get-value API_DEVELOPER_PORTAL_URL)
APIM_NAME=$(azd env get-value API_MANAGEMENT_NAME)

echo ""
echo "🎉 API Management deployment completed!"
echo ""
echo "📋 APIM Information:"
echo "  🌐 API Gateway URL: $API_GATEWAY_URL"
echo "  👥 Developer Portal: $DEVELOPER_PORTAL_URL"
echo "  ⚙️ Management Name: $APIM_NAME"
echo ""

# Configure API operations
echo "🔧 Configuring API operations..."
./scripts/configure-apim-apis.sh

echo ""
echo "✅ API Management setup complete!"
echo ""
echo "🚀 Next Steps:"
echo "1. Visit the Developer Portal: $DEVELOPER_PORTAL_URL"
echo "2. Create API subscriptions for your customers"
echo "3. Update your documentation to point to: $API_GATEWAY_URL"
echo "4. Test the API endpoints through APIM"
echo ""

if [ -n "$CUSTOM_DOMAIN" ]; then
    echo "🌐 Custom Domain Setup:"
    echo "1. Add a CNAME record: $CUSTOM_DOMAIN -> ${APIM_NAME}.azure-api.net"
    echo "2. Wait for SSL certificate provisioning (can take 15-45 minutes)"
    echo "3. Update your documentation URLs once SSL is ready"
    echo ""
fi

echo "💡 Management URLs:"
echo "  Azure Portal: https://portal.azure.com/#resource/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP_NAME/providers/Microsoft.ApiManagement/service/$APIM_NAME"
echo "  API Management: $API_GATEWAY_URL"
