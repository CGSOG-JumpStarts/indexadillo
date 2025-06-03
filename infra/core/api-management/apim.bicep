@description('Name of the API Management service')
param name string

@description('Location for API Management service')
param location string = resourceGroup().location

@description('Tags for the API Management service')
param tags object = {}

@description('API Management SKU tier')
@allowed(['Developer', 'Basic', 'Standard', 'Premium', 'Consumption'])
param tier string = 'Developer'

@description('API Management SKU capacity')
param capacity int = 1

@description('Publisher email for API Management')
param publisherEmail string = 'admin@indexadillo.ai'

@description('Publisher name for API Management')
param publisherName string = 'Indexadillo'

@description('Function App name to integrate with')
param functionAppName string

@description('Function App key for backend authentication')
@secure()
param functionAppKey string = ''

@description('Event Hub connection string for logging')
@secure()
param eventHubConnectionString string = ''

@description('Custom domain name (optional)')
param customDomainName string = ''

@description('Enable Application Insights integration')
param enableAppInsights bool = true

@description('Application Insights instrumentation key')
@secure()
param appInsightsInstrumentationKey string = ''

// API Management service
resource apiManagement 'Microsoft.ApiManagement/service@2023-05-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: tier
    capacity: capacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
    notificationSenderEmail: publisherEmail
    hostnameConfigurations: customDomainName != '' ? [
      {
        type: 'Proxy'
        hostName: customDomainName
        negotiateClientCertificate: false
        defaultSslBinding: true
        certificateSource: 'Managed'
      }
    ] : []
    customProperties: {
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Tls11': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Protocols.Ssl30': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Tls10': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Tls11': 'False'
      'Microsoft.WindowsAzure.ApiManagement.Gateway.Security.Backend.Protocols.Ssl30': 'False'
    }
    virtualNetworkType: 'None'
    disableGateway: false
    apiVersionConstraint: {
      minApiVersion: '2019-12-01'
    }
    publicNetworkAccess: 'Enabled'
  }
}

// Application Insights logger (if enabled)
resource appInsightsLogger 'Microsoft.ApiManagement/service/loggers@2023-05-01-preview' = if (enableAppInsights && appInsightsInstrumentationKey != '') {
  parent: apiManagement
  name: 'appinsights-logger'
  properties: {
    loggerType: 'applicationInsights'
    credentials: {
      instrumentationKey: appInsightsInstrumentationKey
    }
    isBuffered: true
    resourceId: ''
  }
}

// Event Hub logger (if connection string provided)
resource eventHubLogger 'Microsoft.ApiManagement/service/loggers@2023-05-01-preview' = if (eventHubConnectionString != '') {
  parent: apiManagement
  name: 'eventhub-logger'
  properties: {
    loggerType: 'azureEventHub'
    credentials: {
      connectionString: eventHubConnectionString
      name: 'api-logs'
    }
    isBuffered: true
  }
}

// Backend service for Function App
resource functionAppBackend 'Microsoft.ApiManagement/service/backends@2023-05-01-preview' = {
  parent: apiManagement
  name: 'indexadillo-function-backend'
  properties: {
    description: 'Indexadillo Function App Backend'
    url: 'https://${functionAppName}.azurewebsites.net'
    protocol: 'http'
    credentials: functionAppKey != '' ? {
      header: {
        'x-functions-key': [functionAppKey]
      }
    } : {}
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// Named values for configuration
resource namedValues 'Microsoft.ApiManagement/service/namedValues@2023-05-01-preview' = [
  for item in [
    { name: 'function-app-url', value: 'https://${functionAppName}.azurewebsites.net', secret: false }
    { name: 'function-app-key', value: functionAppKey, secret: true }
    { name: 'api-version', value: 'v1', secret: false }
  ]: {
    parent: apiManagement
    name: item.name
    properties: {
      displayName: item.name
      value: item.value
      secret: item.secret
    }
  }
]

// Indexadillo API Product
resource indexadilloProduct 'Microsoft.ApiManagement/service/products@2023-05-01-preview' = {
  parent: apiManagement
  name: 'indexadillo-api'
  properties: {
    displayName: 'Indexadillo Document Processing API'
    description: 'Scalable document processing API for RAG applications. Transform documents into searchable, AI-ready content.'
    subscriptionRequired: true
    approvalRequired: false
    state: 'published'
    subscriptionsLimit: 1000
  }
}

// API definition
resource indexadilloApi 'Microsoft.ApiManagement/service/apis@2023-05-01-preview' = {
  parent: apiManagement
  name: 'indexadillo-api'
  properties: {
    displayName: 'Indexadillo Document Processing API'
    description: 'Scalable document processing API for RAG applications'
    serviceUrl: 'https://${functionAppName}.azurewebsites.net/api/v1'
    path: 'v1'
    protocols: ['https']
    subscriptionRequired: true
    apiVersion: 'v1'
    apiVersionSetId: apiVersionSet.id
    format: 'openapi+json'
    value: loadTextContent('../../../docs/openapi.yaml')
  }
}

// API Version Set
resource apiVersionSet 'Microsoft.ApiManagement/service/apiVersionSets@2023-05-01-preview' = {
  parent: apiManagement
  name: 'indexadillo-versions'
  properties: {
    displayName: 'Indexadillo API Versions'
    versioningScheme: 'Segment'
    description: 'Version set for Indexadillo API'
  }
}

// Link API to Product
resource productApi 'Microsoft.ApiManagement/service/products/apis@2023-05-01-preview' = {
  parent: indexadilloProduct
  name: indexadilloApi.name
}

// Subscription plans
resource developerSubscription 'Microsoft.ApiManagement/service/subscriptions@2023-05-01-preview' = {
  parent: apiManagement
  name: 'developer-plan'
  properties: {
    displayName: 'Developer Plan'
    scope: '/products/${indexadilloProduct.name}'
    state: 'active'
    allowTracing: true
  }
}

// Global policy
resource globalPolicy 'Microsoft.ApiManagement/service/policies@2023-05-01-preview' = {
  parent: apiManagement
  name: 'policy'
  properties: {
    value: loadTextContent('./policies/global-policy.xml')
    format: 'xml'
  }
}

// Product policy
resource productPolicy 'Microsoft.ApiManagement/service/products/policies@2023-05-01-preview' = {
  parent: indexadilloProduct
  name: 'policy'
  properties: {
    value: loadTextContent('./policies/product-policy.xml')
    format: 'xml'
  }
}

// API operations with specific policies
resource documentExtractOperation 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: indexadilloApi
  name: 'document-extract'
  properties: {
    displayName: 'Extract text from documents'
    method: 'POST'
    urlTemplate: '/document/extract'
    description: 'Extract structured text from PDF documents, images, and other file types'
    request: {
      headers: [
        {
          name: 'X-API-Key'
          type: 'string'
          required: true
          description: 'API key for authentication'
        }
      ]
    }
    responses: [
      {
        statusCode: 200
        description: 'Document successfully processed'
        representations: [
          {
            contentType: 'application/json'
          }
        ]
      }
      {
        statusCode: 400
        description: 'Bad request'
      }
      {
        statusCode: 401
        description: 'Unauthorized'
      }
      {
        statusCode: 413
        description: 'Payload too large'
      }
    ]
  }
}

// Operation policy for document processing with timeout
resource documentExtractPolicy 'Microsoft.ApiManagement/service/apis/operations/policies@2023-05-01-preview' = {
  parent: documentExtractOperation
  name: 'policy'
  properties: {
    value: loadTextContent('./policies/document-extract-policy.xml')
    format: 'xml'
  }
}

// Developer portal customization
resource portalConfig 'Microsoft.ApiManagement/service/portalsettings@2023-05-01-preview' = {
  parent: apiManagement
  name: 'signin'
  properties: {
    enabled: true
  }
}

// Diagnostic settings for monitoring
resource diagnosticSetting 'Microsoft.ApiManagement/service/diagnostics@2023-05-01-preview' = if (enableAppInsights) {
  parent: apiManagement
  name: 'applicationinsights'
  properties: {
    alwaysLog: 'allErrors'
    httpCorrelationProtocol: 'W3C'
    verbosity: 'information'
    logClientIp: true
    loggerId: enableAppInsights ? appInsightsLogger.id : ''
    sampling: {
      samplingType: 'fixed'
      percentage: 100
    }
    frontend: {
      request: {
        headers: ['X-API-Key', 'User-Agent']
        body: {
          bytes: 8192
        }
      }
      response: {
        headers: ['X-RateLimit-Remaining']
        body: {
          bytes: 8192
        }
      }
    }
    backend: {
      request: {
        headers: ['X-Functions-Key']
        body: {
          bytes: 8192
        }
      }
      response: {
        headers: ['X-Azure-Ref']
        body: {
          bytes: 8192
        }
      }
    }
  }
}

@description('API Management service name')
output name string = apiManagement.name

@description('API Management service ID')
output id string = apiManagement.id

@description('API Management gateway URL')
output gatewayUrl string = apiManagement.properties.gatewayUrl

@description('API Management management URL')
output managementUrl string = apiManagement.properties.managementApiUrl

@description('API Management developer portal URL')
output developerPortalUrl string = apiManagement.properties.developerPortalUrl

@description('API Management system assigned identity principal ID')
output systemIdentityPrincipalId string = apiManagement.identity.principalId
