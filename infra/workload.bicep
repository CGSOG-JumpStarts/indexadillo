param location string
param token string
param tags object
param production bool
param privateNetworking bool
param entraClientId string
param entraTenantId string
param searchLocation string
param modelLocation string
param extractionLocation string
param embeddingModel string
param embeddingModelVersion string
param embeddingDeployment string
param embeddingCapacity int
param processingProfilePath string
param enrichmentDeployments array
param enableContentUnderstanding bool
param tenantScopes object
param budgetContactEmails array
param monthlyBudget int
param budgetStartDate string

var functionName = 'func-${token}'
var physicalIndex = 'documents-v2'
var effectiveScopes = empty(tenantScopes)
  ? {
      '${entraTenantId}': { tenant_id: entraTenantId, prefix: '${entraTenantId}/', indexes: [physicalIndex] }
    }
  : tenantScopes

resource ingestion 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-ingest-${token}'
  location: location
  tags: tags
}
resource query 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-query-${token}'
  location: location
  tags: tags
}
module host 'storage.bicep' = {
  name: 'host-storage'
  params: {
    name: 'sthost${token}'
    location: location
    tags: tags
    production: production
    privateNetworking: privateNetworking
    containers: ['app-package']
  }
}
module source 'storage.bicep' = {
  name: 'source-storage'
  params: {
    name: 'stsrc${token}'
    location: location
    tags: tags
    production: production
    privateNetworking: privateNetworking
    containers: ['source', 'events-deadletter']
    source: true
  }
}
module artifacts 'storage.bicep' = {
  name: 'artifact-storage'
  params: {
    name: 'start${token}'
    location: location
    tags: tags
    production: production
    privateNetworking: privateNetworking
    containers: ['artifacts', 'manifests', 'locks', 'registry']
  }
}
module network 'network.bicep' = if (privateNetworking) {
  name: 'network'
  params: { name: 'vnet-${token}', location: location, tags: tags }
}

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: 'srch-${token}'
  location: searchLocation
  tags: tags
  sku: { name: 'standard' }
  properties: {
    replicaCount: production ? 3 : 1
    partitionCount: 1
    hostingMode: 'Default'
    disableLocalAuth: true
    publicNetworkAccess: privateNetworking ? 'disabled' : 'enabled'
    semanticSearch: production ? 'standard' : 'free'
  }
}
resource model 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'oai-${token}'
  location: modelLocation
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'oai-${token}'
    disableLocalAuth: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
  }
}
resource embedding 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: model
  name: embeddingDeployment
  sku: { name: 'Standard', capacity: embeddingCapacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModel, version: embeddingModelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}
@batchSize(1)
resource enrichment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for deployment in enrichmentDeployments: {
    parent: model
    name: deployment.name
    sku: { name: deployment.sku, capacity: deployment.capacity }
    properties: {
      model: { format: 'OpenAI', name: deployment.model, version: deployment.version }
      versionUpgradeOption: 'NoAutoUpgrade'
    }
  }
]
resource di 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'di-${token}'
  location: extractionLocation
  tags: tags
  kind: 'FormRecognizer'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'di-${token}'
    disableLocalAuth: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
  }
}
resource cu 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (enableContentUnderstanding) {
  name: 'cu-${token}'
  location: extractionLocation
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'cu-${token}'
    disableLocalAuth: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
  }
}
resource cuUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (enableContentUnderstanding) {
  name: guid(cu!.id, ingestion.id, 'cu-user')
  scope: cu
  properties: {
    principalId: ingestion.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'a97b65f3-24c7-4388-baec-2e87135dc908'
    )
  }
}
module roles 'roles.bicep' = {
  name: 'runtime-roles'
  params: {
    hostStorageName: host.outputs.name
    sourceStorageName: source.outputs.name
    artifactStorageName: artifacts.outputs.name
    searchName: search.name
    openAIName: model.name
    documentIntelligenceName: di.name
    ingestionPrincipalId: ingestion.properties.principalId
    queryPrincipalId: query.properties.principalId
  }
}
module insights 'core/application_insights/application_insights_service.bicep' = {
  name: 'observability'
  params: { name: 'appi-${token}', location: location, tags: tags }
}
resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = { name: 'appi-${token}-ai' }
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${token}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  properties: { reserved: true, zoneRedundant: production }
}
resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: functionName
  location: location
  tags: union(tags, { 'azd-service-name': 'indexadillo-func' })
  kind: 'functionapp,linux'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${ingestion.id}': {}, '${query.id}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'
    virtualNetworkSubnetId: privateNetworking ? network!.outputs.integrationSubnetId : null
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: 'https://${host.outputs.name}.blob.${environment().suffixes.storage}/app-package'
          authentication: { type: 'UserAssignedIdentity', userAssignedIdentityResourceId: ingestion.id }
        }
      }
      runtime: { name: 'python', version: '3.12' }
      scaleAndConcurrency: {
        maximumInstanceCount: production ? 40 : 10
        instanceMemoryMB: 2048
        alwaysReady: production ? [{ name: 'durable', instanceCount: 2 }, { name: 'http', instanceCount: 2 }] : []
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: map(
        items({
          AzureWebJobsStorage__accountName: host.outputs.name
          AzureWebJobsStorage__credential: 'managedidentity'
          AzureWebJobsStorage__clientId: ingestion.properties.clientId
          SOURCE_EVENTS_STORAGE__queueServiceUri: 'https://${source.outputs.name}.queue.${environment().suffixes.storage}'
          SOURCE_EVENTS_STORAGE__credential: 'managedidentity'
          SOURCE_EVENTS_STORAGE__clientId: ingestion.properties.clientId
          AZURE_CLIENT_ID: ingestion.properties.clientId
          QUERY_CLIENT_ID: query.properties.clientId
          SOURCE_STORAGE_ACCOUNT_NAME: source.outputs.name
          ARTIFACT_STORAGE_ACCOUNT_NAME: artifacts.outputs.name
          APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
          AZURE_OPENAI_ENDPOINT: model.properties.endpoint
          DI_ENDPOINT: di.properties.endpoint
          CONTENT_UNDERSTANDING_ENDPOINT: enableContentUnderstanding ? cu!.properties.endpoint : ''
          SEARCH_SERVICE_ENDPOINT: 'https://${search.name}.search.windows.net'
          ENTRA_TENANT_ID: entraTenantId
          ENTRA_AUDIENCE: entraClientId
          TENANT_SCOPES_JSON: string(effectiveScopes)
          AUTH_MODE: 'entra'
          RECONCILIATION_SCHEDULE: '0 0 */6 * * *'
          HISTORY_RETENTION_DAYS: '14'
          BLOB_AMOUNT_PARALLEL: '4'
          EXTRACTION_CONCURRENCY: '4'
          EMBEDDING_CONCURRENCY: '4'
          ENRICHMENT_CONCURRENCY: '2'
          PROCESSING_PROFILE: processingProfilePath
          FUNCTIONS_WORKER_PROCESS_COUNT: '2'
          PYTHON_THREADPOOL_THREAD_COUNT: '8'
        }),
        setting => { name: setting.key, value: setting.value }
      )
    }
  }
  dependsOn: [roles]
}
resource authentication 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: app
  name: 'authsettingsV2'
  properties: {
    platform: { enabled: true, runtimeVersion: '~1' }
    globalValidation: { requireAuthentication: true, unauthenticatedClientAction: 'Return401' }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          openIdIssuer: '${environment().authentication.loginEndpoint}${entraTenantId}/v2.0'
        }
        validation: { allowedAudiences: [entraClientId, 'api://${entraClientId}'] }
      }
    }
    httpSettings: { requireHttps: true }
  }
}

module events 'events.bicep' = {
  name: 'events'
  params: { location: location, name: 'events-${token}', sourceStorageName: source.outputs.name, tags: tags }
}
var privateConnections = concat(
  [
    {
      name: 'host-blob'
      id: resourceId('Microsoft.Storage/storageAccounts', 'sthost${token}')
      group: 'blob'
      zones: ['privatelink.blob.${environment().suffixes.storage}']
    }
    {
      name: 'host-queue'
      id: resourceId('Microsoft.Storage/storageAccounts', 'sthost${token}')
      group: 'queue'
      zones: ['privatelink.queue.${environment().suffixes.storage}']
    }
    {
      name: 'host-table'
      id: resourceId('Microsoft.Storage/storageAccounts', 'sthost${token}')
      group: 'table'
      zones: ['privatelink.table.${environment().suffixes.storage}']
    }
    {
      name: 'source-blob'
      id: resourceId('Microsoft.Storage/storageAccounts', 'stsrc${token}')
      group: 'blob'
      zones: ['privatelink.blob.${environment().suffixes.storage}']
    }
    {
      name: 'source-queue'
      id: resourceId('Microsoft.Storage/storageAccounts', 'stsrc${token}')
      group: 'queue'
      zones: ['privatelink.queue.${environment().suffixes.storage}']
    }
    {
      name: 'artifact-blob'
      id: resourceId('Microsoft.Storage/storageAccounts', 'start${token}')
      group: 'blob'
      zones: ['privatelink.blob.${environment().suffixes.storage}']
    }
    { name: 'search', id: search.id, group: 'searchService', zones: ['privatelink.search.windows.net'] }
    { name: 'model', id: model.id, group: 'account', zones: ['privatelink.openai.azure.com'] }
    { name: 'di', id: di.id, group: 'account', zones: ['privatelink.cognitiveservices.azure.com'] }
    { name: 'function', id: app.id, group: 'sites', zones: ['privatelink.azurewebsites.net'] }
  ],
  enableContentUnderstanding
    ? [
        {
          name: 'cu'
          id: cu!.id
          group: 'account'
          zones: ['privatelink.cognitiveservices.azure.com', 'privatelink.services.ai.azure.com']
        }
      ]
    : []
)
module endpoints 'private-endpoint.bicep' = [
  for i in range(0, length(privateConnections)): if (privateNetworking) {
    name: 'pe-${privateConnections[i].name}'
    params: {
      name: 'pe-${privateConnections[i].name}-${token}'
      location: location
      tags: tags
      subnetId: network!.outputs.endpointSubnetId
      resourceId: privateConnections[i].id
      groupId: privateConnections[i].group
      dnsZoneIds: map(privateConnections[i].zones, zone => network!.outputs.zoneIds[zone])
    }
  }
]
module monitoring 'monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    appInsightsId: appInsights.id
    functionId: app.id
    sourceStorageId: resourceId('Microsoft.Storage/storageAccounts', 'stsrc${token}')
    budgetContactEmails: budgetContactEmails
    monthlyBudget: monthlyBudget
    budgetStartDate: budgetStartDate
  }
}
output functionName string = app.name
output sourceStorage string = source.outputs.name
output artifactStorage string = artifacts.outputs.name
output hostStorage string = host.outputs.name
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output modelEndpoint string = model.properties.endpoint
output extractionEndpoint string = di.properties.endpoint
output contentUnderstandingEndpoint string = enableContentUnderstanding ? cu!.properties.endpoint : ''
output tenantScopesJson string = string(effectiveScopes)
output queryClientId string = query.properties.clientId
