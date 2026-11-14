param location string
param name string
param sourceStorageName string
param tags object

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: sourceStorageName }
resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}
resource queue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' existing = {
  parent: queueService
  name: 'ingestion-events'
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}
resource deadletters 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: blobService
  name: 'events-deadletter'
}
resource topic 'Microsoft.EventGrid/systemTopics@2022-06-15' = {
  name: name
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: { source: storage.id, topicType: 'Microsoft.Storage.StorageAccounts' }
}
resource sender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(queue.id, topic.id, 'queue-sender')
  scope: queue
  properties: {
    principalId: topic.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'c6a89b2d-59bc-44d0-9896-0f6e12d7b80a'
    )
  }
}
resource deadletterWriter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(deadletters.id, topic.id, 'deadletter-writer')
  scope: deadletters
  properties: {
    principalId: topic.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
  }
}
resource subscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2022-06-15' = {
  parent: topic
  name: 'source-lifecycle'
  properties: {
    eventDeliverySchema: 'EventGridSchema'
    filter: {
      subjectBeginsWith: '/blobServices/default/containers/source/blobs/'
      includedEventTypes: ['Microsoft.Storage.BlobCreated', 'Microsoft.Storage.BlobDeleted']
    }
    deliveryWithResourceIdentity: {
      identity: { type: 'SystemAssigned' }
      destination: { endpointType: 'StorageQueue', properties: { resourceId: storage.id, queueName: queue.name } }
    }
    deadLetterWithResourceIdentity: {
      identity: { type: 'SystemAssigned' }
      deadLetterDestination: {
        endpointType: 'StorageBlob'
        properties: { resourceId: storage.id, blobContainerName: deadletters.name }
      }
    }
    retryPolicy: { maxDeliveryAttempts: 30, eventTimeToLiveInMinutes: 1440 }
  }
  dependsOn: [sender, deadletterWriter]
}
