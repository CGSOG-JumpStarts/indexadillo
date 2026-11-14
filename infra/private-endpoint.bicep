param location string
param name string
param subnetId string
param resourceId string
param groupId string
param dnsZoneIds array
param tags object

resource endpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    subnet: { id: subnetId }
    privateLinkServiceConnections: [
      {
        name: name
        properties: { privateLinkServiceId: resourceId, groupIds: [groupId] }
      }
    ]
  }
}

resource group 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: endpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      for (zoneId, i) in dnsZoneIds: { name: 'zone-${i}', properties: { privateDnsZoneId: zoneId } }
    ]
  }
}
