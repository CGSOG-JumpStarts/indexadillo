# Validation record

Implementation baseline: `ab7a6edd7c39a90c51b9f95a8ad46069a10adf47`.
Review date: November 14, 2026. Runtime/test Python: 3.12.14.

## Passed locally

* `pytest --cov=core --cov=activities --cov=orchestrators --cov=function_app`:
  **80 passed**, **83% aggregate statement coverage**. Core lifecycle coverage 99%;
  authentication 93%; model/extraction adapter code 93%. Coverage is not evidence
  of live service acceptance.
* `ruff check src scripts tests` and `ruff format --check src scripts tests`.
* Python compilation of `src`, `scripts` and `tests`.
* Bicep CLI **0.49.2**: main deployment and isolated scheduler templates compile;
  dev and prod `.bicepparam` files compile with dummy configuration values.
* `scripts/check_infrastructure.py` against the compiled main ARM template:
  authentication, HTTPS, storage key/public-blob restrictions, role exclusions,
  managed-identity event dead-letter configuration and private endpoint invariants.
* `pip-audit -r src/requirements.txt --no-deps --disable-pip`:
  **no known vulnerabilities found** in the resolved runtime packages at audit time.
* `git diff --check`.
* Actionlint **1.7.12**: both GitHub Actions workflows validate.

The async API tests require worker-thread shutdown. This workspace's restricted
sandbox hung during Python's event-loop teardown after a passing test; the complete
mocked suite passed outside that sandbox. The tests did not use Azure credentials
or make a live model request.

## Behavior exercised

Signed JWT validation and forged-header rejection; issuer/audience/expiry/role
checks; group overage rejection; source/index scope restrictions; current-source
permission and ETag checks before returning text; authenticated citations; status
redaction; exact-path committed-block and deletion events; duplicate scheduling;
empty-prefix continuation; Durable checkpoints and isolated document failure;
full-path document identity; idempotence; shrinking/empty replacements; delayed
delete protection; interrupted uploads; source-version races; unknown orphan-key
recovery; per-item indexing failures; UTF-8 byte batching; Unicode character/page
spans; token/chunk limits; embedding order/dimensions; actual OpenAI SDK embedding
request serialization through a mocked HTTP transport; artifact/cache reuse across
ETag-only changes; strict stateless Responses metadata with confidence escalation;
incomplete model output; GA layout byte/Markdown configuration; GA Content
Understanding polling and foreign-host rejection; lease release/loss/deadlines;
Retry-After; sanitized activity exceptions; evaluation document-grain calculations.

## Not run

No configured Azure connection was available in this workspace. Consequently no
resources were deployed, no application registration/role assignments changed,
and the existing live-Azure E2E suite was rewritten for the new authenticated
contract but not executed. The full deterministic offline suite passed; a complete
live integration acceptance has not been performed.

Remaining release evidence: Azure resource/provider acceptance, actual regional
model availability/quota/capacity, managed-identity role propagation, private DNS
and connectivity, Functions extension/queue delivery behavior, token acquisition
through the tenant's client applications, alert notification delivery, actual
source corpus retrieval/model quality, billed cost and load/fault/recovery drills.
Optional model routes, knowledge-base objects, and scheduler benchmarks have not
been activated or measured in Azure. The example evaluation JSONL is not a labeled
customer corpus. Follow docs/deployment.md, docs/evaluation.md and docs/migration.md.
