param hostStorageName string
param sourceStorageName string
param artifactStorageName string
param searchName string
param openAIName string
param documentIntelligenceName string
param ingestionPrincipalId string
param queryPrincipalId string

resource host 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: hostStorageName }
resource source 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: sourceStorageName }
resource sourceBlobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: source
  name: 'default'
}
resource sourceContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: sourceBlobs
  name: 'source'
}
resource artifact 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: artifactStorageName }
resource search 'Microsoft.Search/searchServices@2025-05-01' existing = { name: searchName }
resource openAI 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: openAIName }
resource di 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: documentIntelligenceName }
var blobContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var queueContributor = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var hostRoles = ['b7e6dc6d-f1e8-4753-8033-0f276bb0955b', queueContributor, '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3']
resource hostAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in hostRoles: {
    name: guid(host.id, ingestionPrincipalId, role)
    scope: host
    properties: {
      principalId: ingestionPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
    }
  }
]
resource sourceBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(source.id, ingestionPrincipalId, 'blob-reader')
  scope: sourceContainer
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}
resource querySourceReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(source.id, queryPrincipalId, 'blob-reader')
  scope: sourceContainer
  properties: {
    principalId: queryPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}
resource sourceQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(source.id, ingestionPrincipalId, queueContributor)
  scope: source
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueContributor)
  }
}
resource artifactBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: artifact
  name: 'default'
}
var writableContainers = ['artifacts', 'manifests', 'locks']
resource writable 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = [
  for container in writableContainers: { parent: artifactBlobService, name: container }
]
resource artifactWriters 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for (container, i) in writableContainers: {
    name: guid(artifact.id, container, ingestionPrincipalId, blobContributor)
    scope: writable[i]
    properties: {
      principalId: ingestionPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributor)
    }
  }
]
resource registry 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: artifactBlobService
  name: 'registry'
}
resource registryReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, ingestionPrincipalId, 'reader')
  scope: registry
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}
resource searchWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, ingestionPrincipalId, 'writer')
  scope: search
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
    )
  }
}
resource searchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, queryPrincipalId, 'reader')
  scope: search
  properties: {
    principalId: queryPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '1407120a-92aa-4202-b7e9-c0e197c71c8f'
    )
  }
}
resource modelUsers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principal in [ingestionPrincipalId, queryPrincipalId]: {
    name: guid(openAI.id, principal, 'model-user')
    scope: openAI
    properties: {
      principalId: principal
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
      )
    }
  }
]
resource extraction 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(di.id, ingestionPrincipalId, 'extraction-user')
  scope: di
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'a97b65f3-24c7-4388-baec-2e87135dc908'
    )
  }
}
