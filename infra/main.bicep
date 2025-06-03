targetScope = 'subscription'

param environmentName string
param location string

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
    containerNames: [functionContainerName, 'source']
  }
]

module storage 'core/storage/storage-account.bicep' = [
  for storage in  storages:{
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

// API Management if enabled
module apiManagement 'core/api-management/apim.bicep' = if (enableApiManagement) {
  name: 'apiManagement'
  scope: resourceGroup
  params: {
    name: '${abbrs.apiManagementService}${resourceToken}'
    location: location
    tags: tags
    tier: apiTier
    functionAppName: flexFunction.outputs.name
    functionAppKey: flexFunction.outputs.functionKey
    eventHubConnectionString: eventHub.outputs.connectionString
  }
}

// Application Gateway for custom domain and SSL
module applicationGateway 'core/networking/app-gateway.bicep' = if (enableApiManagement) {
  name: 'applicationGateway'
  scope: resourceGroup
  params: {
    name: '${abbrs.networkApplicationGateways}${resourceToken}'
    location: location
    tags: tags
    backendFqdn: enableApiManagement ? apiManagement.outputs.gatewayUrl : flexFunction.outputs.functionAppUrl
  }
}

module flexFunction 'core/host/function-api.bicep' = {
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
    cosmosEndpoint: cosmosDb.outputs.endpoint
    cosmosKey: cosmosDb.outputs.primaryKey
    eventHubConnectionString: eventHub.outputs.connectionString
  }
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

output SOURCE_STORAGE_ACCOUNT_NAME string = storage[0].outputs.storageAccountName

output RESOURCE_GROUP_NAME string = resourceGroup.name
output SYSTEM_TOPIC_NAME string = eventgrid.outputs.systemTopicName
// output FUNCTION_APP_NAME string = functionAppName
output DI_ENDPOINT string = documentIntelligence.outputs.endpoint
output AZURE_OPENAI_ENDPOINT string = openAI.outputs.endpoint
output SEARCH_SERVICE_ENDPOINT string = searchService.outputs.endpoint
output API_ENDPOINT string = enableApiManagement ? apiManagement.outputs.gatewayUrl : flexFunction.outputs.functionAppUrl
output COSMOS_ENDPOINT string = cosmosDb.outputs.endpoint
output EVENT_HUB_NAMESPACE string = eventHub.outputs.namespaceName
output API_MANAGEMENT_NAME string = enableApiManagement ? apiManagement.outputs.name : ''
output FUNCTION_APP_NAME string = flexFunction.outputs.name
