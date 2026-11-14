param name string
param location string
param tags object
param production bool
param privateNetworking bool
param containers array
param source bool = false

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: production ? 'Standard_ZRS' : 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    allowCrossTenantReplication: false
    supportsHttpsTrafficOnly: true
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    // Event Grid delivery uses its system identity and the trusted-service bypass.
    publicNetworkAccess: privateNetworking && !source ? 'Disabled' : 'Enabled'
    networkAcls: { bypass: source ? 'AzureServices' : 'None', defaultAction: privateNetworking ? 'Deny' : 'Allow' }
  }
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 14 }
    containerDeleteRetentionPolicy: { enabled: true, days: 14 }
    isVersioningEnabled: source
  }
}
resource blobs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for container in containers: {
    parent: blobService
    name: container
    properties: { publicAccess: 'None' }
  }
]
resource queues 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = if (source) {
  parent: account
  name: 'default'
}
resource queue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = if (source) {
  parent: queues
  name: 'ingestion-events'
}
resource poison 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = if (source) {
  parent: queues
  name: 'ingestion-events-poison'
}
// Cached artifacts may be regenerated. Manifests/registry are retained for recovery.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = if (!source && contains(
  containers,
  'artifacts'
)) {
  parent: account
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'expire-cache'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['artifacts/'] }
            actions: { baseBlob: { delete: { daysAfterModificationGreaterThan: 90 } } }
          }
        }
      ]
    }
  }
}
output id string = account.id
output name string = account.name
