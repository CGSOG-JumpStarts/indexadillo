// Deploy an isolated benchmark scheduler. Do not switch an existing task hub in place.
param name string
param location string = resourceGroup().location
param ingestionPrincipalId string
@description('Resolve the current built-in Durable Task Data Contributor role definition ID with az role definition list.')
param durableTaskRoleDefinitionId string
@description('Public egress IPs/CIDRs of the benchmark workers. No public access is allowed by default.')
param allowedWorkerIps array = []

resource scheduler 'Microsoft.DurableTask/schedulers@2026-02-01' = {
  name: name
  location: location
  properties: {
    sku: { name: 'Consumption' }
    publicNetworkAccess: 'Enabled'
    ipAllowlist: allowedWorkerIps
  }
}
resource hub 'Microsoft.DurableTask/schedulers/taskHubs@2026-02-01' = {
  parent: scheduler
  name: 'indexadillobenchmark'
}
resource role 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(hub.id, ingestionPrincipalId, durableTaskRoleDefinitionId)
  scope: hub
  properties: {
    principalId: ingestionPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: durableTaskRoleDefinitionId
  }
}
output schedulerId string = scheduler.id
output taskHub string = hub.name
