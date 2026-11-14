# Deployment and identity

This release targets Azure public cloud and Python 3.12. The default backend is
Azure Storage Durable Functions. Source, host/deployment, and processing artifacts
use separate storage accounts. No Azure resource has been deployed by the local
test suite.

## Entra application

Use a single-tenant API application with v2 access tokens, an `api://CLIENT_ID`
identifier URI, and the application roles in [entra-application.json](entra-application.json).
That JSON is a Microsoft Graph application PATCH body, not a complete application
registration. Apply it through your normal tenant administration process. Assign
the appropriate Reader, Indexer, or Operator app role to callers; Operator includes
the other roles in application authorization. A caller that needs both indexing
and search can instead receive both Reader and Indexer.

Configure a delegated API scope for interactive clients if needed. Application
clients request `api://CLIENT_ID/.default`; delegated clients request the scope you
expose. The application validates signatures, issuer, audience, expiry, tenant,
object identity, and app roles. Tokens with group overage claims fail closed: use
scoped groups or a caller mapping rather than silently bypassing missing groups.
Do not grant end users direct Azure Search data-plane roles: custom document
authorization is enforced by this API.

`TENANT_SCOPES_JSON` is server-controlled. A key can be an Entra tenant ID, or
`TENANT_ID:OBJECT_ID` for a specific application/user identity:

```json
{
  "ENTRA_TENANT_ID:APP_OBJECT_ID": {
    "tenant_id": "customer-a",
    "prefix": "customers/a/",
    "indexes": ["customer-a-v2"],
    "query_alias": "customer-a-current",
    "default_groups": []
  }
}
```

Prefixes must be nonempty, end in `/`, and not overlap. Each mapping must have a
unique tenant identifier. Callers cannot override the mapping. Without a custom
mapping, the Bicep deployment routes its Entra tenant to `TENANT_ID/` and the
`documents-v2` physical index. Event ingestion routes each blob into every physical
index configured for that source scope; use this to maintain both sides during
an index migration. An alias is query-only in application configuration.

Blob metadata `allowed_groups` contains comma-separated Entra group IDs.
`visibility=restricted` requires groups; `visibility=tenant` permits authorized
readers in the mapped tenant. Configured `default_groups` force restricted
visibility. Only trusted source writers should set permission metadata.

## Deployment identity

Infrastructure provisioning requires rights to create resources and assign the
scoped runtime roles. Separately grant the deployment identity:

* Search Service Contributor on this Search service to administer schemas/aliases.
* Search Index Data Contributor when running integration tests or inspecting data.
* Storage Blob Data Contributor on the artifact account for index registry and
  cutover tooling; source upload permissions only when needed.

The runtime never receives Search Service Contributor. Its ingestion identity has
document-write and model/extraction permissions, read access to source blobs,
read-only access to the schema registry, and write access to manifests/cache/locks.
The query identity has Search read, source Blob read, and embedding inference.
Source Blob access lets the API reject stale permission metadata before returning
text and serve authenticated citations. Both identities currently reside in one
Function app; this is RBAC separation, not process isolation against compromised
application code.

## Development deployment

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
az login
azd auth login
azd env new indexadillo-dev
azd env set ENTRA_CLIENT_ID YOUR_API_APPLICATION_CLIENT_ID
azd up
```

Select a region supporting Flex Consumption, the chosen Search features,
Document Intelligence, and your embedding deployment. Locations default to that
one region; override `searchLocation`, `modelLocation`, and `extractionLocation`
only after checking availability, latency, and data residency. Quota is not a
guarantee of regional capacity. Default model deployment is regional Standard
`text-embedding-3-large`, version `1`, capacity `20`; verify its quota units for
your subscription. Model versions and upgrade behavior are explicit.

The postdeploy hook provisions all configured physical indexes and writes their
profile fingerprints into the registry. It parses azd outputs as data without
shell evaluation. New role assignments can need time to propagate; the index
provisioner retries authorization failures for a bounded period.

Upload documents beneath the configured prefix in the `source` container.
Uploading outside it does not grant access or schedule work.

## Production profile

`infra/profiles/prod.bicepparam` enables ZRS storage, three Search replicas,
zone-redundant Flex hosting, always-ready HTTP/Durable instances, VNet integration,
private endpoints, and private DNS. It needs a region supporting those features.

```sh
export AZURE_ENV_NAME=indexadillo-prod AZURE_LOCATION=YOUR_COMPATIBLE_REGION
export ENTRA_CLIENT_ID=YOUR_API_APPLICATION_CLIENT_ID
az deployment sub what-if --location "$AZURE_LOCATION" \
  --template-file infra/main.bicep --parameters infra/profiles/prod.bicepparam
```

Review the resulting plan before deploying through your normal release process.
An azd production environment can use the equivalent main-template parameters.
Do not deploy a production profile over an undrained v1 task hub; follow
[migration.md](migration.md).

Production deployment, schema provisioning, tests and API clients need network
access through the VNet or connected network, including private SCM DNS. A public
GitHub-hosted runner cannot reach private endpoints. Use a VNet-connected runner.
The default GitHub integration workflow deploys development resources only.

Event Grid delivers with its system identity into Storage Queue through the
Storage trusted-service firewall exception. The source account retains a public
service endpoint with default-deny firewall rules and that exception. The worker
consumes the queue over Private Link. This is not an exclusively private-IP Event
Grid delivery path. All other production data services disable public access.

Private-link DNS, deployment package access, queue polling, source reads, model
calls, extraction, JWT key discovery, telemetry, and authenticated citations must
all be exercised in the actual network before promotion. JWT validation needs
outbound HTTPS to the tenant's Microsoft Entra signing-key endpoint.

Supply `budgetContactEmails` and `monthlyBudget` to activate a one-year monthly
budget and route alerts to operators. A budget alerts on spending; it is not a
spend cap. Configure notification recipients and test alert delivery.

## Optional model routes

Retain [documents-v2.yaml](../src/profiles/documents-v2.yaml) as the baseline.
Create a separate profile and physical index for each candidate. Set
`processingProfilePath` to the packaged profile's relative path in the deployed
Function app and `PROCESSING_PROFILE` to that file's local path for CLI tools.
Embedding model/deployment/dimensions must match the Bicep model deployment.

Enrichment is disabled by default. To enable it, explicitly provision the chosen
Azure model deployments through `enrichmentDeployments` and set the profile's
`enrichment.enabled`, deployment/model, fallback deployment/model and request
budgets. Supported examples are `gpt-6-luna` for routine metadata and
`gpt-6.1-sol` for lower-confidence escalation. The route uses Azure v1 Responses,
strict JSON schema, bounded input/output, configured reasoning/verbosity, and
`store:false`. It has no tools, conversation chaining, or background responses.
`store:false` does not establish Zero Data Retention; confirm your Azure retention
and processing/residency requirements before enabling an optional route.

For Content Understanding, set `enableContentUnderstanding=true`, configure its
supported analyzer/model dependencies in the Foundry resource, then use provider
`content-understanding`, API `2025-11-01`, and the analyzer ID in the profile.
The adapter uploads bytes directly and validates the polling host. Provisioning
the account alone does not configure custom analyzers or model dependencies.
CU page numbers are returned only where the service explicitly supplies
page-scoped provenance; missing page information is not fabricated.

Preview query planning, answer synthesis, native ACL integrations, serverless
Search, and agentic document understanding are not production defaults. Evaluate
them in separate resources with the relevant current API and regional terms.
