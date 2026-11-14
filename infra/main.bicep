targetScope = 'subscription'

param environmentName string
param location string
@description('Single-tenant Entra API application configured with v2 access tokens and application roles.')
param entraClientId string
param entraTenantId string = tenant().tenantId
param production bool = false
param privateNetworking bool = production
param searchLocation string = location
param modelLocation string = location
param extractionLocation string = location
param embeddingModel string = 'text-embedding-3-large'
param embeddingModelVersion string = '1'
param embeddingDeployment string = 'embedding'
param embeddingCapacity int = 20
param processingProfilePath string = 'profiles/documents-v2.yaml'
@description('Explicit additional Azure model deployments for optional enrichment. Empty by default.')
param enrichmentDeployments array = []
param enableContentUnderstanding bool = false
@description('Override with an explicit mapping from Entra tenant or tenant:object ID to source/index scope.')
param tenantScopes object = {}
param budgetContactEmails array = []
param monthlyBudget int = 500
param budgetStartDate string = utcNow('yyyy-MM-01')

var token = toLower(uniqueString(subscription().id, environmentName, location))
resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: { 'azd-env-name': environmentName, workload: 'indexadillo', environment: production ? 'prod' : 'dev' }
}
module workload 'workload.bicep' = {
  name: 'indexadillo'
  scope: group
  params: {
    location: location
    token: token
    tags: group.tags
    production: production
    privateNetworking: privateNetworking
    entraClientId: entraClientId
    entraTenantId: entraTenantId
    searchLocation: searchLocation
    modelLocation: modelLocation
    extractionLocation: extractionLocation
    embeddingModel: embeddingModel
    embeddingModelVersion: embeddingModelVersion
    embeddingDeployment: embeddingDeployment
    embeddingCapacity: embeddingCapacity
    processingProfilePath: processingProfilePath
    enrichmentDeployments: enrichmentDeployments
    enableContentUnderstanding: enableContentUnderstanding
    tenantScopes: tenantScopes
    budgetContactEmails: budgetContactEmails
    monthlyBudget: monthlyBudget
    budgetStartDate: budgetStartDate
  }
}
output RESOURCE_GROUP_NAME string = group.name
output FUNCTION_APP_NAME string = workload.outputs.functionName
output SOURCE_STORAGE_ACCOUNT_NAME string = workload.outputs.sourceStorage
output ARTIFACT_STORAGE_ACCOUNT_NAME string = workload.outputs.artifactStorage
output HOST_STORAGE_ACCOUNT_NAME string = workload.outputs.hostStorage
output SEARCH_SERVICE_ENDPOINT string = workload.outputs.searchEndpoint
output AZURE_OPENAI_ENDPOINT string = workload.outputs.modelEndpoint
output DI_ENDPOINT string = workload.outputs.extractionEndpoint
output CONTENT_UNDERSTANDING_ENDPOINT string = workload.outputs.contentUnderstandingEndpoint
output TENANT_SCOPES_JSON string = workload.outputs.tenantScopesJson
output ENTRA_AUDIENCE string = entraClientId
output ENTRA_TENANT_ID string = entraTenantId
output QUERY_CLIENT_ID string = workload.outputs.queryClientId
output PRIVATE_NETWORKING bool = privateNetworking
