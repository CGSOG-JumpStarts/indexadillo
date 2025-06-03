@description('Name of the Cosmos DB account')
param name string

@description('Location for the Cosmos DB account')
param location string = resourceGroup().location

@description('Tags for the Cosmos DB account')
param tags object = {}

@description('Database definitions')
param databases array = []

@description('Consistency level for the Cosmos DB account')
@allowed(['Eventual', 'ConsistentPrefix', 'Session', 'BoundedStaleness', 'Strong'])
param consistencyLevel string = 'Session'

@description('Enable automatic failover')
param enableAutomaticFailover bool = false

@description('Enable multiple write locations')
param enableMultipleWriteLocations bool = false

resource cosmosDbAccount 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: name
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    consistencyPolicy: {
      defaultConsistencyLevel: consistencyLevel
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    databaseAccountOfferType: 'Standard'
    enableAutomaticFailover: enableAutomaticFailover
    enableMultipleWriteLocations: enableMultipleWriteLocations
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    backupPolicy: {
      type: 'Periodic'
      periodicModeProperties: {
        backupIntervalInMinutes: 1440
        backupRetentionIntervalInHours: 720
        backupStorageRedundancy: 'Local'
      }
    }
  }
}

// Create databases and containers
resource databases_resource 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = [
  for database in databases: {
    parent: cosmosDbAccount
    name: database.name
    properties: {
      resource: {
        id: database.name
      }
    }
  }
]

resource containers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-11-15' = [
  for (database, dbIndex) in databases: {
    parent: databases_resource[dbIndex]
    name: database.containers[0].name
    properties: {
      resource: {
        id: database.containers[0].name
        partitionKey: {
          paths: [database.containers[0].partitionKey]
          kind: 'Hash'
        }
        defaultTtl: -1
      }
    }
  }
]

@description('Cosmos DB account name')
output name string = cosmosDbAccount.name

@description('Cosmos DB account ID')
output id string = cosmosDbAccount.id

@description('Cosmos DB endpoint')
output endpoint string = cosmosDbAccount.properties.documentEndpoint

@description('Cosmos DB primary key')
output primaryKey string = cosmosDbAccount.listKeys().primaryMasterKey

@description('Cosmos DB connection string')
output connectionString string = 'AccountEndpoint=${cosmosDbAccount.properties.documentEndpoint};AccountKey=${cosmosDbAccount.listKeys().primaryMasterKey};'
