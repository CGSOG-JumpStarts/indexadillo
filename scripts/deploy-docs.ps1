# PowerShell version for Windows

Write-Host "🚀 Deploying API Documentation to Azure Static Web Apps..." -ForegroundColor Green

# Check if Azure CLI is installed
if (!(Get-Command "az" -ErrorAction SilentlyContinue)) {
    Write-Error "Azure CLI is required but not installed"
    exit 1
}

# Check if logged in to Azure
try {
    az account show | Out-Null
} catch {
    Write-Error "Please log in to Azure CLI first: az login"
    exit 1
}

# Load environment variables
$envName = $env:AZURE_ENV_NAME ?? "indexadillo-dev"
$envFile = ".azure/$envName/.env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            Set-Variable -Name $matches[1] -Value $matches[2].Trim('"')
        }
    }
    Write-Host "✅ Loaded environment variables from $envFile" -ForegroundColor Green
} else {
    Write-Error "Environment file not found: $envFile"
    Write-Host "Run 'azd env get-values' to create it"
    exit 1
}

# Set variables
$resourceGroup = $env:RESOURCE_GROUP_NAME ?? "rg-$envName"
$staticWebAppName = "swa-docs-$envName"
$location = $env:AZURE_LOCATION ?? "East US 2"

Write-Host "📋 Configuration:" -ForegroundColor Cyan
Write-Host "  Resource Group: $resourceGroup"
Write-Host "  Static Web App: $staticWebAppName"
Write-Host "  Location: $location"

# Create static web app if it doesn't exist
Write-Host "🏗️ Creating Static Web App..." -ForegroundColor Yellow

try {
    az staticwebapp show --name $staticWebAppName --resource-group $resourceGroup | Out-Null
    Write-Host "ℹ️ Static Web App already exists" -ForegroundColor Blue
} catch {
    az staticwebapp create `
        --name $staticWebAppName `
        --resource-group $resourceGroup `
        --location $location `
        --sku "Free" `
        --source "https://github.com/your-username/indexadillo" `
        --branch "main" `
        --app-location "/docs" `
        --output-location "" `
        --login-with-github
    
    Write-Host "✅ Static Web App created successfully" -ForegroundColor Green
}

# Get deployment token and deploy
$deploymentToken = az staticwebapp secrets list `
    --name $staticWebAppName `
    --resource-group $resourceGroup `
    --query "properties.apiKey" `
    --output tsv

if (!$deploymentToken) {
    Write-Error "Failed to get deployment token"
    exit 1
}

# Install SWA CLI if needed
if (!(Get-Command "swa" -ErrorAction SilentlyContinue)) {
    Write-Host "📥 Installing Azure Static Web Apps CLI..." -ForegroundColor Yellow
    npm install -g @azure/static-web-apps-cli
}

# Deploy
Write-Host "📦 Deploying static content..." -ForegroundColor Yellow
Set-Location docs
swa deploy --deployment-token $deploymentToken --app-location "." --output-location "." --env "production"
Set-Location ..

# Get URL
$appUrl = az staticwebapp show `
    --name $staticWebAppName `
    --resource-group $resourceGroup `
    --query "defaultHostname" `
    --output tsv

Write-Host ""
Write-Host "🎉 Documentation deployed successfully!" -ForegroundColor Green
Write-Host "📖 Documentation URL: https://$appUrl" -ForegroundColor Cyan
Write-Host ""
