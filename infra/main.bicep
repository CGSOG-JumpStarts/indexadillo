targetScope = 'subscription'

param environmentName string
param location string

// APIM Configuration
param enableApiManagement bool = false
param apiManagementTier string = 'Developer'
param publisherEmail string = 'admin@aijumpstarts.com'
param publisherName string = 'aijumpstarts'
param customDomainName string = ''

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

var functionAppName = '${abbrs.webSitesFunctions}${resourceToken}'
var functionContainerName = 'app-package-${functionAppName}'

var tags = { 'azd-env-name': environmentName }

resource resourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  location: location
  tags: tags
  name: '${abbrs.resourcesResourceGroups}${environmentName}'
}

// Existing infrastructure modules
module userAssignedIdentity 'core/identity/user-assigned-identity.bicep' = {
  name: 'UserAssignedIdentity'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    identityName: '${abbrs.managedIdentityUserAssignedIdentities}${resourceToken}'
  }
}

var storages = [
  {
    name: 'sourceStorage'
    storageAccountName: '${abbrs.storageStorageAccounts}source${resourceToken}'
    containerNames: [functionContainerName, 'source', 'api-temp']
  }
]

module storage 'core/storage/storage-account.bicep' = [
  for storage in storages: {
    name: storage.name
    scope: resourceGroup
    params: {
      location: location
      tags: tags
      storageAccountName: storage.storageAccountName
      containerNames: storage.containerNames
    }
  }
]

module documentIntelligence 'core/cognitive_services/document_intelligence.bicep' = {
  name: 'documentIntelligence'
  scope: resourceGroup
  params: {
    name: '${abbrs.cognitiveServicesAccounts}doc-int-${resourceToken}'
    location: 'westeurope'
    tags: tags
    sourceStorageAccountName: storage[0].outputs.storageAccountName
  }
}

module openAI 'core/cognitive_services/openai.bicep' = {
  name: 'openAI'
  scope: resourceGroup
  params: {
    name: '${abbrs.cognitiveServicesAccounts}ai-${resourceToken}'
    location: 'swedencentral'
    tags: tags
  }
}

module searchService 'core/search/search-service.bicep' = {
  name: 'searchService'
  scope: resourceGroup
  params: {
    name: '${abbrs.searchSearchServices}ai-${resourceToken}'
    location: 'switzerlandnorth'
    tags: tags
    openAIName: openAI.outputs.name
  }
}

module appInsights 'core/application_insights/application_insights_service.bicep' = {
  name: 'appInsights'
  scope: resourceGroup
  params: {
    name: '${abbrs.insightsComponents}${resourceToken}'
    location: location
    tags: tags
  }
}

// Cosmos DB for API user management (only if APIM is enabled)
module cosmosDb 'core/database/cosmos-db.bicep' = if (enableApiManagement) {
  name: 'cosmosDb'
  scope: resourceGroup
  params: {
    name: '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
    location: location
    tags: tags
    databases: [
      {
        name: 'indexadillo_api'
        containers: [
          { name: 'api_users', partitionKey: '/id' }
          { name: 'api_usage', partitionKey: '/user_id' }
          { name: 'api_keys', partitionKey: '/key_hash' }
        ]
      }
    ]
  }
}

// Event Hub for APIM logging (only if APIM is enabled)
module eventHub 'core/messaging/event-hub.bicep' = if (enableApiManagement) {
  name: 'eventHub'
  scope: resourceGroup
  params: {
    namespaceName: '${abbrs.eventHubNamespaces}${resourceToken}'
    eventHubName: 'api-logs'
    location: location
    tags: tags
  }
}

module flexFunction 'core/host/function.bicep' = {
  name: 'functionapp'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    appInsightsName: appInsights.outputs.name
    openAIName: openAI.outputs.name
    documentIntelligenceName: documentIntelligence.outputs.name
    sourceStorageAccountName: storage[0].outputs.storageAccountName
    FunctionPlanName: '${abbrs.webServerFarms}${resourceToken}'
    functionAppName: functionAppName
    identityId: userAssignedIdentity.outputs.identityId
    identityClientId: userAssignedIdentity.outputs.identityClientId
    principalID: userAssignedIdentity.outputs.identityPrincipalId
    functionContainerName: functionContainerName
    searchServiceEndpoint: searchService.outputs.endpoint
    diEndpoint: documentIntelligence.outputs.endpoint
    openAIEndpoint: openAI.outputs.endpoint
    searchServiceName: searchService.outputs.name
    // Add APIM-related settings
    cosmosEndpoint: enableApiManagement ? cosmosDb.outputs.endpoint : ''
    cosmosKey: enableApiManagement ? cosmosDb.outputs.primaryKey : ''
    eventHubConnectionString: enableApiManagement ? eventHub.outputs.connectionString : ''
  }
}

// Get function app key for APIM backend configuration
resource functionApp 'Microsoft.Web/sites@2023-12-01' existing = {
  name: functionAppName
  scope: resourceGroup
}

// API Management (optional)
module apiManagement 'core/api-management/apim.bicep' = if (enableApiManagement) {
  name: 'apiManagement'
  scope: resourceGroup
  params: {
    name: '${abbrs.apiManagementService}${resourceToken}'
    location: location
    tags: tags
    tier: apiManagementTier
    publisherEmail: publisherEmail
    publisherName: publisherName
    functionAppName: functionAppName
    functionAppKey: listkeys('${flexFunction.outputs.id}/host/default', '2023-12-01').functionKeys.default
    eventHubConnectionString: enableApiManagement ? eventHub.outputs.connectionString : ''
    customDomainName: customDomainName
    enableAppInsights: true
    appInsightsInstrumentationKey: appInsights.outputs.instrumentationKey
  }
  dependsOn: [
    flexFunction
  ]
}

module eventgrid 'core/integration/eventgrid.bicep' = {
  name: 'eventgrid'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    storageAccountName: storage[0].outputs.storageAccountName
    systemTopicName: '${abbrs.eventGridDomainsTopics}${resourceToken}'
  }
}

// Outputs
output SOURCE_STORAGE_ACCOUNT_NAME string = storage[0].outputs.storageAccountName
output RESOURCE_GROUP_NAME string = resourceGroup.name
output SYSTEM_TOPIC_NAME string = eventgrid.outputs.systemTopicName
output FUNCTION_APP_NAME string = functionAppName
output DI_ENDPOINT string = documentIntelligence.outputs.endpoint
output AZURE_OPENAI_ENDPOINT string = openAI.outputs.endpoint
output SEARCH_SERVICE_ENDPOINT string = searchService.outputs.endpoint

// APIM outputs (conditional)
output API_MANAGEMENT_NAME string = enableApiManagement ? apiManagement.outputs.name : ''
output API_GATEWAY_URL string = enableApiManagement ? apiManagement.outputs.gatewayUrl : ''
output API_DEVELOPER_PORTAL_URL string = enableApiManagement ? apiManagement.outputs.developerPortalUrl : ''
output API_MANAGEMENT_URL string = enableApiManagement ? apiManagement.outputs.managementUrl : ''

// Cosmos DB outputs (conditional)
output COSMOS_ENDPOINT string = enableApiManagement ? cosmosDb.outputs.endpoint : ''
output EVENT_HUB_NAMESPACE string = enableApiManagement ? eventHub.outputs.namespaceName : ''
