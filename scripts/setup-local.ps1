# PowerShell script to populate local.settings.json from Azure deployment

Write-Host "Setting up local development environment..." -ForegroundColor Green

# Check if azd is available
if (!(Get-Command "azd" -ErrorAction SilentlyContinue)) {
    Write-Error "azd is required but not installed"
    exit 1
}

# Load environment variables from azd
Write-Host "Loading environment variables from azd..." -ForegroundColor Yellow
try {
    $envOutput = azd env get-values
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get azd environment variables"
    }
} catch {
    Write-Error "Failed to get azd environment variables. Make sure you've run 'azd up' first"
    exit 1
}

# Parse environment variables
$envVars = @{}
foreach ($line in $envOutput) {
    if ($line -match '^([^=]+)=(.*)$') {
        $key = $matches[1]
        $value = $matches[2] -replace '^"', '' -replace '"$', ''
        $envVars[$key] = $value
        Set-Variable -Name $key -Value $value -Scope Global
    }
}

Write-Host "Found environment: $($envVars['AZURE_ENV_NAME'])" -ForegroundColor Cyan

# Get additional values from Azure CLI
Write-Host "Getting additional Azure information..." -ForegroundColor Yellow

# Get Application Insights instrumentation key
try {
    $appInsightsKey = az monitor app-insights component show `
        --resource-group $envVars['RESOURCE_GROUP_NAME'] `
        --app $envVars['RESOURCE_GROUP_NAME'] `
        --query "instrumentationKey" `
        --output tsv 2>$null
} catch {
    $appInsightsKey = ""
}

# Get managed identity client ID
try {
    $managedIdentityClientId = az functionapp identity show `
        --name $envVars['FUNCTION_APP_NAME'] `
        --resource-group $envVars['RESOURCE_GROUP_NAME'] `
        --query "userAssignedIdentities.*.clientId" `
        --output tsv 2>$null
} catch {
    $managedIdentityClientId = ""
}

# Get Cosmos DB info if it exists
try {
    $cosmosEndpoint = az cosmosdb show `
        --name "cosmos-$($envVars['AZURE_ENV_NAME'])" `
        --resource-group $envVars['RESOURCE_GROUP_NAME'] `
        --query "documentEndpoint" `
        --output tsv 2>$null
    
    $cosmosKey = az cosmosdb keys list `
        --name "cosmos-$($envVars['AZURE_ENV_NAME'])" `
        --resource-group $envVars['RESOURCE_GROUP_NAME'] `
        --query "primaryMasterKey" `
        --output tsv 2>$null
} catch {
    $cosmosEndpoint = ""
    $cosmosKey = ""
}

# Create local.settings.json
Write-Host "Creating src/local.settings.json..." -ForegroundColor Yellow

$localSettings = @{
    IsEncrypted = $false
    Values = @{
        "AzureWebJobsStorage" = "UseDevelopmentStorage=true"
        "FUNCTIONS_WORKER_RUNTIME" = "python"
        "AzureWebJobsFeatureFlags" = "EnableWorkerIndexing"
        
        "SOURCE_STORAGE_ACCOUNT_NAME" = $envVars['SOURCE_STORAGE_ACCOUNT_NAME']
        "DI_ENDPOINT" = $envVars['DI_ENDPOINT']
        "AZURE_OPENAI_ENDPOINT" = $envVars['AZURE_OPENAI_ENDPOINT']
        "SEARCH_SERVICE_ENDPOINT" = $envVars['SEARCH_SERVICE_ENDPOINT']
        
        "AZURE_CLIENT_ID" = $managedIdentityClientId
        "APPINSIGHTS_INSTRUMENTATIONKEY" = $appInsightsKey
        
        "BLOB_AMOUNT_PARALLEL" = "20"
        "SEARCH_INDEX_NAME" = "default-index"
        "BLOB_CONTAINER_NAME" = "source"
    }
}

# Add Cosmos DB settings if available
if ($cosmosEndpoint) {
    $localSettings.Values["COSMOS_ENDPOINT"] = $cosmosEndpoint
    $localSettings.Values["COSMOS_KEY"] = $cosmosKey
}

# Convert to JSON and save
$json = $localSettings | ConvertTo-Json -Depth 3
$json | Out-File -FilePath "src/local.settings.json" -Encoding UTF8

Write-Host "✅ Successfully created src/local.settings.json" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Start Azurite: Use VS Code command palette -> 'Azurite: Start'"
Write-Host "2. Run the function app: Press F5 in VS Code or use 'func start' in src/ directory"
Write-Host ""
Write-Host "Variables loaded:" -ForegroundColor Yellow
Write-Host "  Storage Account: $($envVars['SOURCE_STORAGE_ACCOUNT_NAME'])"
Write-Host "  Function App: $($envVars['FUNCTION_APP_NAME'])"
Write-Host "  Resource Group: $($envVars['RESOURCE_GROUP_NAME'])"
if ($cosmosEndpoint) {
    Write-Host "  Cosmos DB: Configured ✅" -ForegroundColor Green
} else {
    Write-Host "  Cosmos DB: Not found (API features will use dev mode)" -ForegroundColor Yellow
}
