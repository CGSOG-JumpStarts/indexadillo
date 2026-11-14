param location string
param tags object
param appInsightsId string
param functionId string
param sourceStorageId string
param budgetContactEmails array
param monthlyBudget int
param budgetStartDate string

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'indexadillo-operations'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'indexadillo'
    enabled: true
    emailReceivers: [
      for (email, i) in budgetContactEmails: { name: 'operator-${i}', emailAddress: email, useCommonAlertSchema: true }
    ]
  }
}
resource failures 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'indexadillo-document-failures'
  location: location
  tags: tags
  properties: {
    displayName: 'Indexadillo document processing failures'
    description: 'Inspect the manifest and replay only failed documents. See docs/operations.md.'
    enabled: true
    severity: 2
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [appInsightsId]
    criteria: {
      allOf: [
        {
          query: 'traces | where message startswith "document_failed"'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    actions: { actionGroups: [actionGroup.id] }
  }
}
resource errors 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'indexadillo-http-errors'
  location: 'global'
  tags: tags
  properties: {
    description: 'Sustained HTTP failures'
    severity: 2
    enabled: true
    scopes: [functionId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'http5xx'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'Http5xx'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 10
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}
resource queueBacklog 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'indexadillo-queue-backlog'
  location: 'global'
  tags: tags
  properties: {
    description: 'Queue backlog includes the poison queue; inspect queue metrics and manifests.'
    severity: 2
    enabled: true
    scopes: ['${sourceStorageId}/queueServices/default']
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'queue-count'
          criterionType: 'StaticThresholdCriterion'
          metricName: 'QueueMessageCount'
          metricNamespace: 'Microsoft.Storage/storageAccounts/queueServices'
          operator: 'GreaterThan'
          threshold: 100
          timeAggregation: 'Average'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = if (!empty(budgetContactEmails)) {
  name: 'indexadillo-monthly'
  properties: {
    category: 'Cost'
    amount: monthlyBudget
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate, endDate: dateTimeAdd(budgetStartDate, 'P1Y') }
    notifications: {
      Actual80Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: budgetContactEmails
      }
      Forecast100Percent: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: budgetContactEmails
      }
    }
  }
}
