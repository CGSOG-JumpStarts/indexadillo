@description('Name of the Event Hub namespace')
param namespaceName string

@description('Name of the Event Hub')
param eventHubName string

@description('Location for the Event Hub namespace')
param location string = resourceGroup().location

@description('Tags for the Event Hub namespace')
param tags object = {}

@description('Event Hub namespace SKU')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Standard'

@description('Event Hub namespace capacity')
param capacity int = 1

@description('Message retention in days')
param messageRetentionInDays int = 7

@description('Partition count')
param partitionCount int = 4

resource eventHubNamespace 'Microsoft.EventHub/namespaces@2023-01-01-preview' = {
  name: namespaceName
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
    capacity: capacity
  }
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
    zoneRedundant: false
    isAutoInflateEnabled: false
    maximumThroughputUnits: 0
    kafkaEnabled: false
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2023-01-01-preview' = {
  parent: eventHubNamespace
  name: eventHubName
  properties: {
    messageRetentionInDays: messageRetentionInDays
    partitionCount: partitionCount
    status: 'Active'
  }
}

// Authorization rule for API Management
resource eventHubAuthRule 'Microsoft.EventHub/namespaces/eventhubs/authorizationRules@2023-01-01-preview' = {
  parent: eventHub
  name: 'apim-logger-rule'
  properties: {
    rights: ['Send']
  }
}

// Namespace-level authorization rule
resource namespaceAuthRule 'Microsoft.EventHub/namespaces/authorizationRules@2023-01-01-preview' = {
  parent: eventHubNamespace
  name: 'RootManageSharedAccessKey'
  properties: {
    rights: ['Listen', 'Manage', 'Send']
  }
}

@description('Event Hub namespace name')
output namespaceName string = eventHubNamespace.name

@description('Event Hub name')
output eventHubName string = eventHub.name

@description('Event Hub namespace ID')
output namespaceId string = eventHubNamespace.id

@description('Event Hub connection string')
output connectionString string = namespaceAuthRule.listKeys().primaryConnectionString

@description('Event Hub connection string for APIM')
output apimConnectionString string = eventHubAuthRule.listKeys().primaryConnectionString
