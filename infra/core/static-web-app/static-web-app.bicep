# Bicep template for Azure Static Web Apps

@description('Name of the static web app')
param name string

@description('Location for the static web app')
param location string = resourceGroup().location

@description('Tags for the static web app')
param tags object = {}

@description('SKU for the static web app')
@allowed(['Free', 'Standard'])
param sku string = 'Free'

@description('Repository URL')
param repositoryUrl string = ''

@description('Repository branch')
param branch string = 'main'

@description('Repository token for GitHub integration')
@secure()
param repositoryToken string = ''

resource staticWebApp 'Microsoft.Web/staticSites@2022-03-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    repositoryUrl: repositoryUrl
    branch: branch
    repositoryToken: repositoryToken
    buildProperties: {
      appLocation: '/docs'
      apiLocation: ''
      outputLocation: ''
      skipGithubActionWorkflowGeneration: true
    }
    stagingEnvironmentPolicy: 'Enabled'
    allowConfigFileUpdates: true
    provider: 'GitHub'
    enterpriseGradeCdnStatus: 'Disabled'
  }
}

// Custom domain (optional)
resource customDomain 'Microsoft.Web/staticSites/customDomains@2022-03-01' = if (!empty(repositoryUrl)) {
  parent: staticWebApp
  name: 'docs.indexadillo.ai'
  properties: {
    validationMethod: 'cname-delegation'
  }
}

// Environment variables for the static web app
resource appSettings 'Microsoft.Web/staticSites/config@2022-03-01' = {
  parent: staticWebApp
  name: 'appsettings'
  properties: {
    API_BASE_URL: 'https://api.indexadillo.ai/v1'
    DOCS_VERSION: '1.0.0'
    ANALYTICS_ID: 'GA_MEASUREMENT_ID'
  }
}

output staticWebAppUrl string = staticWebApp.properties.defaultHostname
output staticWebAppId string = staticWebApp.id
output staticWebAppName string = staticWebApp.name
