# Retrieval and model evaluation

Run `pytest` for deterministic mocked correctness tests. They do not measure
live model quality, network connectivity, Azure capacity, deployment acceptance or
end-to-end cost. The explicit Azure integration workflow verifies authenticated
ingestion, full-path document identity, hybrid retrieval, scope checks and deletion
against temporary resources. Its CI identity must already hold the required Entra
app roles; the workflow's temporary Azure role assignments cannot grant Entra roles.

## Build a labeled corpus

Copy `tests/fixtures/evaluation.example.jsonl` into an ignored evaluation-results
directory. Replace every example with documents and queries representative of your
actual workload: multilingual material, tables, scanned pages, same-named files,
short/long documents, ambiguous queries, exact identifiers and permission-negative
cases. The example is a format illustration, not a quality benchmark.

Each row identifies a query, physical index/alias, relevant source files, optionally
expected source pages, and forbidden source files. Have reviewers label relevance
and citations independently of the model's own confidence. Use separate identities
for Reader, restricted groups and other tenants when evaluating permissions.

```sh
python scripts/evaluation/evaluate.py \
  --url https://YOUR-FUNCTION.azurewebsites.net \
  --audience api://YOUR-API-CLIENT-ID \
  --cases evaluation-results/cases.jsonl \
  --output evaluation-results/baseline.json --min-recall 0.8
```

The runner obtains a token through Azure Identity, compares keyword, vector,
hybrid and hybrid-plus-semantic modes, and reports document-level recall@k, MRR,
nDCG@k, citation checks, and end-to-end p50/p95 latency. Duplicate chunks do not
inflate document recall. A forbidden source fails immediately. The default recall
gate is an illustrative starting point; agree your release threshold before
using it. Missing page labels produce no citation-accuracy claim.

## Candidate comparisons

Create a new profile and physical index for each materially different extraction,
chunking or embedding candidate. Provision matching model deployments. Use a
separate app/environment when comparing incompatible query embedding profiles;
one deployed API has one query embedding profile. Never mix vectors from different
models or dimensions in one field.

Suggested experiment sequence:

1. Existing large embeddings, 3,072 dimensions, hybrid retrieval.
2. Same embeddings with reduced dimensions and scalar/binary compression.
3. Small embeddings with a matching new index and query configuration.
4. Layout-aware extraction versus Content Understanding on rich documents.
5. Optional bounded metadata enrichment, including confidence-based escalation.
6. A multimodal embedding provider where native visual matching materially helps.
   This release's embedding adapter supports Azure OpenAI text embeddings. A new
   provider requires its own ingestion/query adapter, profile validation and
   compatibility tests; the repository does not claim untested Cohere compatibility.

Compare quality, citation accuracy, ingestion latency, retrieval latency, storage,
actual Azure billed cost and processing failures. Include repeated queries, cold
and warm application behavior, and actual source permission checks in latency.
Do not select a newer model solely from its catalog position or self-reported
confidence. Enrichment confidence is a routing signal, not calibrated accuracy.

## Durable Task Scheduler benchmark

`infra/scheduler.bicep` provisions an isolated Consumption scheduler/task hub. Its
worker IP allowlist is empty by default. Resolve the built-in role definition ID
with `az role definition list --name 'Durable Task Data Contributor'` and supply
approved worker egress CIDRs. A production private-endpoint adoption needs a
separate network design and validation.

`scripts/select_backend.py --backend scheduler --output /tmp/host.scheduler.json`
emits a staged host file with the scheduler provider and isolated hub. Configure
`DURABLE_TASK_SCHEDULER_CONNECTION_STRING` using the scheduler's verified endpoint,
`TaskHub=indexadillobenchmark;Authentication=ManagedIdentity;ClientID=WORKER_CLIENT_ID`.
The extension bundle minimum is 4.32.0. Deploy this configuration only to an
isolated benchmark worker with matching scoped permissions and data/index routing.

Compare the same corpus, concurrency, failure scenarios, queue latency, replay
cost and Azure charges against the Storage backend. The tooling does not migrate
in-flight history. Drain the old backend and plan rollback before selecting a new
production backend. No live backend performance result is claimed by this release.
