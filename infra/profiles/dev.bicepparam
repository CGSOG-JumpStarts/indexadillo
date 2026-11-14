using '../main.bicep'
param environmentName = readEnvironmentVariable('AZURE_ENV_NAME')
param location = readEnvironmentVariable('AZURE_LOCATION')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID')
param production = false
param privateNetworking = false
