# PowerShell version for Windows

Write-Host "🚀 Deploying Azure API Management for Indexadillo..." -ForegroundColor Green

# Check prerequisites
if (!(Get-Command "az" -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI is required but not installed"
    exit 1
}

if (!(Get-Command "azd" -ErrorAction SilentlyContinue)) {
    Write-Error "Azure Developer CLI (azd) is required but not installed"
    exit 1
}

# Check if logged in
try {
    az account show | Out-Null
} catch {
    Write-Error "Please log in to Azure CLI first: az login"
    exit 1
}

# Parameters
param(
    [string]$ApimTier = "Developer",
    [string]$PublisherEmail = "admin@indexadillo.ai", 
    [string]$PublisherName = "Indexadillo",
    [string]$CustomDomain = ""
)

# Load environment variables
$envName = $env:AZURE_ENV_NAME ?? "indexadillo-dev"
$envFile = ".azure/$envName/.env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            Set-Variable -Name $matches[1] -Value $matches[2].Trim('"') -Scope Global
        }
    }
    Write-Host "✅ Loaded environment variables from $envFile" -ForegroundColor Green
} else {
    Write-Error "Environment file not found: $envFile"
    Write-Host "Run 'azd env get-values' first or deploy the base infrastructure"
    exit 1
}

Write-Host "📋 APIM Configuration:" -ForegroundColor Cyan
Write-Host "  Environment: $envName"
Write-Host "  Tier: $ApimTier"
Write-Host "  Publisher Email: $PublisherEmail"
Write-Host "  Publisher Name: $PublisherName"
Write-Host "  Custom Domain: $(if ($CustomDomain) { $CustomDomain } else { '(none)' })"
Write-Host ""

# Confirm deployment
$confirmation = Read-Host "🤔 Deploy API Management with these settings? (y/N)"
if ($confirmation -notmatch '^[Yy]$') {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Red
    exit 1
}

# Update azd environment
Write-Host "⚙️ Updating azd environment..." -ForegroundColor Yellow
azd env set ENABLE_API_MANAGEMENT true
azd env set API_MANAGEMENT_TIER $ApimTier
azd env set PUBLISHER_EMAIL $PublisherEmail
azd env set PUBLISHER_NAME $PublisherName

if ($CustomDomain) {
    azd env set CUSTOM_DOMAIN_NAME $CustomDomain
}

# Update parameters to enable APIM
Write-Host "🏗️ Deploying infrastructure with API Management..." -ForegroundColor Yellow

$parameters = @{
    '$schema' = "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"
    'contentVersion' = "1.0.0.0"
    'parameters' = @{
        'environmentName' = @{ 'value' = '${AZURE_ENV_NAME}' }
        'location' = @{ 'value' = '${AZURE_LOCATION}' }
        'enableApiManagement' = @{ 'value' = $true }
        'apiManagementTier' = @{ 'value' = $ApimTier }
        'publisherEmail' = @{ 'value' = $PublisherEmail }
        'publisherName' = @{ 'value' = $PublisherName }
        'customDomainName' = @{ 'value' = $CustomDomain }
    }
}

$parameters | ConvertTo-Json -Depth 4 | Out-File "infra/main.parameters.json" -Encoding UTF8

# Deploy with azd
Write-Host "📦 Running azd provision..." -ForegroundColor Yellow
azd provision --no-prompt

# Get deployment outputs
Write-Host "📊 Getting deployment information..." -ForegroundColor Yellow
$apiGatewayUrl = azd env get-value API_GATEWAY_URL
$developerPortalUrl = azd env get-value API_DEVELOPER_PORTAL_URL  
$apimName = azd env get-value API_MANAGEMENT_NAME

Write-Host ""
Write-Host "🎉 API Management deployment completed!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 APIM Information:" -ForegroundColor Cyan
Write-Host "  🌐 API Gateway URL: $apiGatewayUrl"
Write-Host "  👥 Developer Portal: $developerPortalUrl"
Write-Host "  ⚙️ Management Name: $apimName"
Write-Host ""
