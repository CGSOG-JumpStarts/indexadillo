# Upgrade and rollback

This changes the API contract, identity requirements, task hub, index schema and
storage layout. Deploy alongside the v1 installation first. Do not reinterpret
old Durable histories using the new activities, or write v2 chunks into an old
index. The default v2 task hub is `indexadillov2`.

## Release sequence

1. Back up the existing configuration, source inventory and index definitions.
   Stop accepting new v1 ingestion work and drain existing orchestrations. Keep
   its source/index available for rollback.
2. Configure Entra roles and tenant routing. Copy documents to their mapped source
   prefixes in the new source account; copying does not preserve all metadata by
   default, so explicitly preserve and verify permission metadata.
3. Provision v2 infrastructure and the matching physical index with the deployment
   identity. Runtime identities cannot create or change schemas.
4. Run a complete scoped reindex with reconciliation. Inspect failures and pending
   manifests, then run labeled retrieval and permission evaluations.
5. Point authorized application readers to a stable alias. Keep both physical
   indexes synchronized during the validation window where possible.
6. Test rollback and recovery. Retire the previous deployment only after the
   agreed observation and retention periods.

Old HTTP clients must now send an Entra bearer token. `POST /api/index` returns
HTTP 202 and JSON `{id,statusUrl}`, with a Location header, instead of a plain job
ID. `/api/status/{id}` enforces scope and hides inputs/errors; history requires
Operator. Unbounded `/api/status` enumeration is removed. Search defaults to hybrid
with semantic reranking; `mode=keyword|vector|hybrid` and `semantic=false` support
evaluation. Results contain original source character spans, page lists where
known, and an authenticated `citationUrl`. A citation request also needs a bearer
token; applications should fetch it through their authenticated client.

## Index and model cutover

```sh
PROCESSING_PROFILE=src/profiles/documents-v2.yaml \
  python scripts/manage_search.py create-index --index documents-v2
python scripts/manage_search.py alias --index documents-v2 \
  --alias documents-current --record cutover-v2.json
```

Use server-side `query_alias` configuration for reader traffic and physical index
names in `indexes` for ingestion. The alias tool validates the target schema,
records the previous mapping with exclusive file creation, switches the alias,
waits for propagation and verifies it. It never deletes the old index. For rollback,
use the old matching profile/index and a new cutover record, then restore the
matching query deployment/configuration. Switching an alias alone cannot correct
an incompatible query embedding model or vector dimension.

Treat changed extraction/chunking implementations as profile/schema changes too.
Bump `profile_id`/schema version when changing semantics; the fingerprint detects
configuration differences, not arbitrary future source-code changes.

## Optional managed knowledge binding

The GA Search `2026-04-01` path supports search-index knowledge sources and minimal,
extractive knowledge bases. `scripts/manage_search.py knowledge` provisions these
objects using a physical index; index aliases cannot be knowledge-source targets.

Custom application permission filters do not automatically secure direct knowledge
retrieval. This tool permits only an explicitly tenant-isolated physical index
containing tenant-wide content. It records a registry policy that rejects future
restricted/cross-tenant publication. Pause ingestion and drain active publications
before using `--confirm-ingestion-drained`. An existing restricted document causes
the binding to fail. Restrict knowledge-base access to appropriately scoped service
identities. This optional direct path has eventual permission propagation; keep
restricted content behind the application retrieval route with live source checks.

```sh
python scripts/manage_search.py knowledge --index customer-a-v2 \
  --source customer-a-source --base customer-a-knowledge \
  --confirm-ingestion-drained
```

Coordinate knowledge-source rebinding separately from an application alias
cutover. Check Search's knowledge retrieval billing consent/plan before production
use. LLM query planning, answer synthesis and native document ACL integrations
remain separate preview experiments; no preview API is used by the default runtime.

## Framework alignment

| Pillar | Implemented controls | Production evidence still required |
|---|---|---|
| Security | JWT roles, scope mapping, Search filters, current-source checks, protected citations, scoped identities, private endpoints | Tenant app-role assignments, network/permission-negative tests, retention decisions |
| Reliability | Durable retries, manifest intent, leases, obsolete-key cleanup, deletion, poison/dead-letter paths, reconciliation | Fault injection, recovery drill, regional recovery plan, approved objectives |
| Performance | Bounded payloads, cache references, token/byte batches, per-service distributed slots, hybrid retrieval | Corpus load/latency tests and actual quota/capacity checks |
| Cost | Reused artifacts/batches, compression, retention, explicit model deployments, optional budget | Azure billing comparison and cost per successful publication |
| Operations | Stable profiles, schema registry, cutover records, offline CI, gated live tests, alerts and runbooks | Deployed smoke tests, alert delivery and signed release evidence |

References checked for this modernization on November 14, 2026:

* https://learn.microsoft.com/en-us/azure/well-architected/ai/get-started
* https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle
* https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview
* https://learn.microsoft.com/en-us/azure/search/search-how-to-alias
* https://learn.microsoft.com/en-us/azure/durable-task/durable-functions/durable-functions-serialization-and-persistence
* https://learn.microsoft.com/en-us/azure/event-grid/deliver-events-using-managed-identity
* https://learn.microsoft.com/en-us/azure/reliability/reliability-functions
