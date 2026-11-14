# Operations and recovery

## Processing contract

Events are delivered at least once. Documents are identified by a SHA-256 of
tenant, account, container and full blob path. Each source version plus processing
profile produces deterministic chunk keys. Retries reuse content-addressed
extraction, chunks and per-batch embedding artifacts. A successful embedding batch
is checkpointed before the next batch, so a throttled activity can resume without
rebilling all preceding batches.

Durable history carries references and small routing/profile metadata. It does
not carry source text, embeddings or SAS credentials. Downstream exception bodies
are normalized before the Durable extension persists them. Each publication has
a renewable 60-second lease, renewed every 20 seconds. Failed renewals stop further
guarded writes. Separate renewable slot leases bound downstream concurrency across
Function instances. Provider HTTP retries honor Retry-After and transient errors;
Durable activity retries remain bounded.

Lease deadlines also expire locally if a renewal request is blocked. Search
cannot fence an already in-flight write with a Blob lease; subsequent reconciliation
enumerates all keys for a document and removes unknown orphan generations as well
as the keys recorded in its manifest. This repair adds Search reads to unchanged
document reconciliation and should be included in throughput/cost measurements.

Publication writes a pending manifest before uploading, checks the source ETag
again, removes obsolete keys, and records the published generation. Search has
no multi-document transaction: a replacement can temporarily expose mixed
generations and Search visibility is eventually consistent. The API additionally
checks current source ETags and permission metadata before returning search text
or a citation. Changed, deleted or newly restricted sources fail closed while
reindexing catches up. Source metadata/storage availability is therefore part of
the read path; monitor that latency and availability.

Default limits are 50 MB per source, 512 chunks per document, 512 tokens per chunk,
64-token overlap, four parallel documents per listing page, and token/item limits
per embedding request. Profiles can raise the chunk cap to 2,000; benchmark memory,
activity timeouts, downstream capacity and cost first. Documents exceeding limits
fail into the manifest ledger. They do not silently truncate indexed content.

Collection orchestration checkpoints after 25 listing pages. Empty prefixes
advance to the next prefix. Document failures are counted separately; inspect
`output.failed` even when a collection's Durable runtime status is Completed.
If failure-ledger persistence itself fails, the orchestration can fail and needs
operator recovery. Reconciliation scans current sources and missing manifest
sources every six hours by default, repairing missed events and partial attempts.

## Storage and retention

| Data | Default treatment |
|---|---|
| Source blobs | Authoritative data; source versioning and 14-day soft delete |
| Cached extraction/chunks/embeddings | Artifact account, private container, 90-day cache lifecycle |
| Manifests and registry | Retained for recovery and schema compatibility |
| Durable terminal history | Purged after 14 days |
| Event delivery failures | `events-deadletter` container |
| Queue handler failures | `ingestion-events-poison` queue after five dequeue attempts |

Index deletion propagation is not an erasure guarantee across caches, source
versions, backups and logs. Establish a separate erasure policy and purge those
copies when required. Review retention against customer requirements before
production deployment. Do not store document text in troubleshooting tickets.

## Failure recovery

1. Inspect the tenant/index/document manifest. It preserves both published and
   pending chunk keys even after an interrupted upload.
2. Correct the dependency, quota, permissions or document issue. Runtime logs use
   document hashes, stage names and error types; correlate through Application
   Insights distributed traces for detailed operator diagnostics.
3. Submit `POST /api/index` with the authorized source prefix and `reconcile:true`.
   Replay is idempotent. Existing content caches avoid repeating unchanged model
   calls; failed embedding batches are retried from their cached predecessors.
4. Confirm zero failed documents, expected Search results, no stale chunk keys,
   and correct access behavior. A collection runtime status alone is insufficient.

Inspect poison messages and Event Grid dead letters separately. Correct the
cause before replaying an event; replay the original event ID and source URL into
the queue using an authorized operational identity. If its orchestration already
exists and failed, use a scoped reindex/reconciliation job instead of relying on
duplicate event delivery. Do not automatically loop poison messages indefinitely.

For immediate access revocation, remove the source permission or change its ETag;
the application read path rejects old indexed versions. Confirm negative access
tests. Consumers of a separately provisioned knowledge base must have their own
permission design; custom application filters do not automatically apply there.

## Monitoring

The template provisions failure, HTTP error, queue backlog alerts and an action
group. Email delivery requires `budgetContactEmails`. Tune thresholds to measured
load and test notification delivery. Add service-specific diagnostic categories
under your organization policy; do not enable prompt/body logging by default.

Useful Application Insights queries:

```kusto
traces
| where message startswith "document_failed"
| summarize failures=count() by bin(timestamp, 15m)
```

```kusto
traces
| where message startswith "activity_completed"
| extend stage=extract(@"stage=(\S+)", 1, message),
         duration_ms=todouble(extract(@"duration_ms=([0-9.]+)", 1, message))
| summarize p50=percentile(duration_ms, 50), p95=percentile(duration_ms, 95) by stage
```

Track publication success/failure, source-to-publication freshness, stage durations,
downstream throttling, cache hits, embedding input tokens, enrichment input/output/
cached tokens, queue age/count, poison messages, Search storage/vector capacity,
retrieval/citation latency, retrieval relevance and current Azure billed cost.
Token logs are usage evidence, not a dollar estimate: join them with deployment-
specific Azure rates and page/compute/storage charges. Cost per published document
must include failed/retried work. Never count a completed orchestration as a
published document without checking its result.

## Reliability objectives

Before production promotion, set approved targets for freshness, retrieval latency,
availability, recovery time, recovery point, quality, and cost. Alert on sustained
breaches. The production template's three Search replicas and zone-redundant
hosting improve resilience; they do not establish an end-to-end SLA by themselves.

Exercise: model 429s, Search partial failures, process termination during upload,
source overwrite during extraction, expired/lost lease, delayed/reordered events,
revoked permissions, deleted/recreated blobs, queue delivery failure and regional
dependency loss. Retain the test results in the release evidence.

Treat Search as rebuildable derived data. Preserve source, profiles, manifests and
schema definitions through the organization's backup/recovery policy. For a
regional recovery, provision compatible services, validate data processing location
and quota, restore source data, provision a new physical index, reconcile, evaluate,
then switch the application alias. Availability-zone redundancy is not a regional
disaster-recovery strategy.
