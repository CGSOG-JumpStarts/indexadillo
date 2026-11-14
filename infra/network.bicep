param location string
param name string
param tags object

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.40.0.0/16'] }
    subnets: [
      {
        name: 'functions'
        properties: {
          addressPrefix: '10.40.0.0/24'
          delegations: [{ name: 'functions', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'private-endpoints'
        properties: { addressPrefix: '10.40.1.0/24', privateEndpointNetworkPolicies: 'Disabled' }
      }
    ]
  }
}

var zoneNames = [
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.queue.${environment().suffixes.storage}'
  'privatelink.table.${environment().suffixes.storage}'
  'privatelink.search.windows.net'
  'privatelink.openai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.azurewebsites.net'
]

resource zones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in zoneNames: {
    name: zone
    location: 'global'
    tags: tags
  }
]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, i) in zoneNames: {
    parent: zones[i]
    name: name
    location: 'global'
    properties: { registrationEnabled: false, virtualNetwork: { id: vnet.id } }
  }
]

output integrationSubnetId string = '${vnet.id}/subnets/functions'
output endpointSubnetId string = '${vnet.id}/subnets/private-endpoints'
var zoneOutputs = [for (zone, i) in zoneNames: { name: zone, id: zones[i].id }]
output zoneIds object = toObject(zoneOutputs, item => item.name, item => item.id)
