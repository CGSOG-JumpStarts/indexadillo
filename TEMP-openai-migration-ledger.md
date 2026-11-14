# OpenAI API Migration Decision Ledger

**Application:** Indexadillo, baseline ab7a6edd7c39a90c51b9f95a8ad46069a10adf47.
**Current integration:** Azure OpenAI embeddings through dated 2024-02-15-preview; no existing generative chat path.
**Selected integration and model:** Azure-only managed identity; v1 embeddings, text-embedding-3-large baseline. Optional stateless Azure Responses metadata using configured gpt-6-luna/gpt-6.1-sol deployments; GA Document Intelligence and optional GA Content Understanding.
**Approved migration scope and feature-stage plan:** On 2026-11-14 the user requested: “Implement all the suggested changes.” All five stages authorized in one pass: API security; lifecycle correctness; retrieval; production infrastructure; model evolution/evaluation. Code and offline verification implemented. Azure deployment, tenant configuration and empirical corpus/provider benchmarks require the actual connected Azure environment and labeled corpus.
**Privacy and retention requirements:** Preserve Azure provider and managed identity. Source/cache/manifest retention is explicit in docs/operations.md; no SAS or source content in Durable references. Enrichment is single-turn store:false and disabled by default. No ZDR or jurisdiction requirement was supplied; production policy verification remains outstanding and store:false is not claimed as ZDR.
**Assessment or implementation:** Implementation on feat/production-modernization-2026; no live Azure calls or deployments.

Review every item against the application, selected model and provider, developer decisions, and approved scope. Add rows for newly documented capabilities or workload-specific differences; under the migration section, use one row per required workflow or invocation mode, even when sharing a provider, with its selected route, retained alternatives, code/documentation changes, and validation commands/results. Replace every placeholder with a concise, developer-visible decision; never claim a capability was implemented or tested without supporting evidence.

**Applicable:** Whether the capability benefits the application's behavior, workloads, or product requirements: `yes`, `no`, or `unknown`; support alone does not establish applicability.
**Supported:** Whether the selected model, provider, framework, and SDK can provide the capability: `yes`, `no`, `partial`, or `unknown`.
**Decision:** The capability's agreed migration outcome: `pending`, `implemented`, `already present`, `deferred`, `unsupported`, or `not applicable`. Use `deferred` only for a feature-specific developer decision or concrete blocker; justify `unsupported` or `not applicable` with capability or workload evidence.
**Implemented:** Mark `[x]` only after approved implementation is complete and verified; leave `[ ]` for pending, deferred, unsupported, or inapplicable items.
**Rationale or evidence:** The brief product, compatibility, privacy, cost, or scope justification; include the planned stage and developer-decision receipt, or relevant code, tests, and versioned official documentation.

## Model Selection

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Record a concrete supported model recommendation and suitability for each workload; models may be shared. | yes | yes | implemented | [x] | Versioned profiles retain large embeddings; small/reduced-dimension alternatives, optional bounded metadata and corpus evaluation documented. tests/unit/test_models.py, test_pipeline.py, test_evaluation.py; empirical model ranking remains unmeasured. |
| Preserve an appropriate existing model; confirm material model or capability-tier changes. | yes | yes | implemented | [x] | Versioned profiles retain large embeddings; small/reduced-dimension alternatives, optional bounded metadata and corpus evaluation documented. tests/unit/test_models.py, test_pipeline.py, test_evaluation.py; empirical model ranking remains unmeasured. |
| Account for workload quality, speed, latency, and cost. | yes | yes | implemented | [x] | Versioned profiles retain large embeddings; small/reduced-dimension alternatives, optional bounded metadata and corpus evaluation documented. tests/unit/test_models.py, test_pipeline.py, test_evaluation.py; empirical model ranking remains unmeasured. |

## Instruction File Naming

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve existing instruction files; add compatibility files only with explicit approval, without renaming or rewriting existing files. | yes | yes | already present | [x] | No instruction files were renamed or added; existing repository conventions preserved. |

## Migrate from Chat Completions to the Responses API

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Migrate applicable OpenAI workloads to the Responses API. | yes | yes | implemented | [x] | No legacy chat calls exist. Existing embeddings remain embeddings and use Azure v1; the new optional metadata path uses Responses. Approved authentication/API/schema changes are documented in docs/migration.md. |
| Preserve existing product behavior and approved provider compatibility. | yes | yes | implemented | [x] | No legacy chat calls exist. Existing embeddings remain embeddings and use Azure v1; the new optional metadata path uses Responses. Approved authentication/API/schema changes are documented in docs/migration.md. |

## Streaming

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve existing streaming and user-visible output behavior. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Add streaming only where responsiveness benefits justify the approved change. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Adapt typed Responses streaming events to existing rendering and consumption paths. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Preserve complete-response workflows and defer disproportionate implementation changes. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |

## WebSocket Mode

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess persistent transport for long-running or tool-heavy workflows. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Preserve existing HTTP and streaming behavior when WebSockets add insufficient value. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Handle structured errors, failed or incomplete responses, and provider-specific concurrency limits; OpenAI allows one active response per `stream_id` lane, with concurrent lanes. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Recover failed turns according to storage and Zero Data Retention requirements. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |
| Reconnect safely without duplicating visible output or side-effecting tool calls. | no | unknown | not applicable | [ ] | Background ingestion and bounded machine-readable metadata need completed responses, not interactive generated text. Existing HTTP retrieval is buffered. No stream, WebSocket, reconnect or tool loop is introduced. |

## Data Privacy and Residency

### Zero Data Retention

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Explicitly confirm Zero Data Retention and other retention requirements. | unknown | partial | pending | [ ] | No tenant-specific jurisdiction or ZDR policy supplied. Region parameters default to one region; optional enrichment remains disabled. Deployment must validate Azure processing location, retention and feature/model compatibility. docs/deployment.md. |
| Verify endpoint, model, feature, tool, caching, and background-execution compatibility. | yes | partial | implemented | [x] | Azure provider retained; optional Responses uses store:false with no chaining/background/tools. Cache/history retention explicit; no SAS in state. These controls do not establish ZDR or erase all retained copies. |
| Configure stateless storage behavior when required. | yes | partial | implemented | [x] | Azure provider retained; optional Responses uses store:false with no chaining/background/tools. Cache/history retention explicit; no SAS in state. These controls do not establish ZDR or erase all retained copies. |
| Preserve existing privacy and storage expectations. | yes | partial | implemented | [x] | Azure provider retained; optional Responses uses store:false with no chaining/background/tools. Cache/history retention explicit; no SAS in state. These controls do not establish ZDR or erase all retained copies. |

### Data Residency

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Identify required storage and processing jurisdictions. | unknown | partial | pending | [ ] | No tenant-specific jurisdiction or ZDR policy supplied. Region parameters default to one region; optional enrichment remains disabled. Deployment must validate Azure processing location, retention and feature/model compatibility. docs/deployment.md. |
| Verify project settings, regional endpoints, and regional model or feature availability. | unknown | partial | pending | [ ] | No tenant-specific jurisdiction or ZDR policy supplied. Region parameters default to one region; optional enrichment remains disabled. Deployment must validate Azure processing location, retention and feature/model compatibility. docs/deployment.md. |
| Confirm residency or regional-processing tradeoffs with the developer. | unknown | partial | pending | [ ] | No tenant-specific jurisdiction or ZDR policy supplied. Region parameters default to one region; optional enrichment remains disabled. Deployment must validate Azure processing location, retention and feature/model compatibility. docs/deployment.md. |

## Processing Tiers

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess tier requirements separately for each distinct workload. | yes | yes | implemented | [x] | Baseline Azure embeddings retain regional Standard processing; new deployments are explicit IaC input. Metadata and ingestion budgets are independent; no paid tier automatically enabled. docs/deployment.md and docs/evaluation.md. |
| Standard processing. | yes | yes | implemented | [x] | Baseline Azure embeddings retain regional Standard processing; new deployments are explicit IaC input. Metadata and ingestion budgets are independent; no paid tier automatically enabled. docs/deployment.md and docs/evaluation.md. |
| Priority processing. | no | unknown | not applicable | [ ] | No Priority/Flex/Batch/Reserved feature was requested in the accepted roadmap. No provider-specific tier substitution is made; regional availability, cost and completion objectives need live Azure evaluation before selecting another tier. |
| Flex processing. | no | unknown | not applicable | [ ] | No Priority/Flex/Batch/Reserved feature was requested in the accepted roadmap. No provider-specific tier substitution is made; regional availability, cost and completion objectives need live Azure evaluation before selecting another tier. |
| Batch processing. | no | unknown | not applicable | [ ] | No Priority/Flex/Batch/Reserved feature was requested in the accepted roadmap. No provider-specific tier substitution is made; regional availability, cost and completion objectives need live Azure evaluation before selecting another tier. |
| Reserved processing. | no | unknown | not applicable | [ ] | No Priority/Flex/Batch/Reserved feature was requested in the accepted roadmap. No provider-specific tier substitution is made; regional availability, cost and completion objectives need live Azure evaluation before selecting another tier. |
| Confirm pricing, latency, availability, retention, and developer preferences. | no | unknown | not applicable | [ ] | No Priority/Flex/Batch/Reserved feature was requested in the accepted roadmap. No provider-specific tier substitution is made; regional availability, cost and completion objectives need live Azure evaluation before selecting another tier. |

## Prompt Caching

### Prompt Cache Keys

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| For GPT-5.6 and later, omit new cache keys by default and preserve existing keys; for earlier models, use stable cache keys for reusable prompt prefixes. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |
| Avoid cache-key and prefix fragmentation. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |

### Extended Cache Retention for Earlier Models

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess extended retention for eligible models against developer retention requirements. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |

### Explicit Cache Breakpoints for GPT-5.6 and Later

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Apply supported explicit breakpoints to stable, reusable content. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |
| Choose implicit or explicit-only caching according to conversation and privacy requirements; record any breakpoint deferral separately. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |

### Prompt Cache Diagnostics

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Plan how to obtain a suitable comparison response ID and use `prompt_cache_options.comparison_response_id` on eligible GPT-5.6-and-later Responses requests; record evidenced workflow or retained-framework limitations. | no | partial | not applicable | [ ] | Optional metadata has a short fixed instruction prefix and independent bounded single-turn calls. No substantial reusable prompt prefix or comparison response ID exists. Content-addressed artifact and embedding-batch caching avoids repeat calls; prompt retention/breakpoints are not enabled. |

## State Management

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Select local or server-side state according to architecture, privacy, and developer approval. | no | unknown | not applicable | [ ] | Metadata is independent single-turn extraction, with store:false. No conversation, previous_response_id, reasoning/tool replay or instruction persistence across turns. Source artifacts and Durable job state remain application-owned. |
| Preserve complete conversation, reasoning, tool-call, and tool-output replay for stateless workflows. | no | unknown | not applicable | [ ] | Metadata is independent single-turn extraction, with store:false. No conversation, previous_response_id, reasoning/tool replay or instruction persistence across turns. Source artifacts and Durable job state remain application-owned. |
| Use stored-response chaining only when retention is permitted and approved. | no | unknown | not applicable | [ ] | Metadata is independent single-turn extraction, with store:false. No conversation, previous_response_id, reasoning/tool replay or instruction persistence across turns. Source artifacts and Durable job state remain application-owned. |

### Instruction Persistence Gotcha

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve durable instructions across stateless replay and stored-response chaining. | no | unknown | not applicable | [ ] | Metadata is independent single-turn extraction, with store:false. No conversation, previous_response_id, reasoning/tool replay or instruction persistence across turns. Source artifacts and Durable job state remain application-owned. |
| Replay instruction input items or resend top-level instructions when required. | no | unknown | not applicable | [ ] | Metadata is independent single-turn extraction, with store:false. No conversation, previous_response_id, reasoning/tool replay or instruction persistence across turns. Source artifacts and Durable job state remain application-owned. |

## Reasoning

### Encrypted Reasoning Items

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve complete encrypted reasoning items across stateless turns and tool calls. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |
| Preserve original ordering, encrypted payloads, and tool-call identifiers. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |
| Avoid replacing original reasoning items with summaries or reconstructed text. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |

### Reasoning Effort

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Explicitly configure supported reasoning effort for each applicable model and workload. | yes | yes | implemented | [x] | Optional supported GPT-6-family metadata profiles set configurable reasoning effort (low baseline), with explicit input/output budgets. Tests cover stateless strict-schema calls and incomplete-response failure. No cross-turn reasoning history exists. |
| Preserve established preferences or confirm new quality, latency, and cost tradeoffs. | yes | yes | implemented | [x] | Optional supported GPT-6-family metadata profiles set configurable reasoning effort (low baseline), with explicit input/output budgets. Tests cover stateless strict-schema calls and incomplete-response failure. No cross-turn reasoning history exists. |
| Verify selected model and provider support. | yes | yes | implemented | [x] | Optional supported GPT-6-family metadata profiles set configurable reasoning effort (low baseline), with explicit input/output budgets. Tests cover stateless strict-schema calls and incomplete-response failure. No cross-turn reasoning history exists. |

### Reasoning Preservation

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess supported cross-turn versus current-turn reasoning preservation. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |
| Preserve required history while respecting context size, latency, privacy, and developer preferences. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |

### Reasoning Summaries and Tool-Call Preambles

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess reasoning summaries and tool-call preambles for the existing product experience. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |
| Preserve existing user-visible behavior and distinguish summaries from verbosity and message phases. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |
| Verify selected model, provider, and SDK support. | no | unknown | not applicable | [ ] | No conversational continuation or tool loop. Independent bounded metadata requests do not replay encrypted reasoning, preserve cross-turn context, display summaries or emit tool-call preambles. |

## Verbosity

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Configure supported response verbosity for each applicable request. | yes | yes | implemented | [x] | Optional metadata route explicitly sets configurable text.verbosity (low baseline), with strict machine-readable schema. tests/unit/test_models.py. |
| Preserve established preferences or ask the developer before selecting a new setting. | yes | yes | implemented | [x] | Optional metadata route explicitly sets configurable text.verbosity (low baseline), with strict machine-readable schema. tests/unit/test_models.py. |
| Confirm output-length, user-experience, latency, cost, model, and provider compatibility. | yes | yes | implemented | [x] | Optional metadata route explicitly sets configurable text.verbosity (low baseline), with strict machine-readable schema. tests/unit/test_models.py. |

## Maximum Output Tokens

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve existing output limits when appropriate. | yes | yes | implemented | [x] | New optional bounded metadata extraction uses configurable max_output_tokens, default 2048 including reasoning; incomplete responses fail and cannot publish partial metadata. No existing generation limit is changed. |
| Avoid inventing a limit without an application or developer requirement. | yes | yes | implemented | [x] | New optional bounded metadata extraction uses configurable max_output_tokens, default 2048 including reasoning; incomplete responses fail and cannot publish partial metadata. No existing generation limit is changed. |
| Account for both visible output and reasoning tokens. | yes | yes | implemented | [x] | New optional bounded metadata extraction uses configurable max_output_tokens, default 2048 including reasoning; incomplete responses fail and cannot publish partial metadata. No existing generation limit is changed. |

## Assistant Message Phases

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve supported assistant-message phases across requests and replay. | no | unknown | not applicable | [ ] | No assistant history or output-item replay is sent: this application extracts one strict metadata object per independent request. |
| Retain structured assistant outputs rather than collapsing them to plain text. | no | unknown | not applicable | [ ] | No assistant history or output-item replay is sent: this application extracts one strict metadata object per independent request. |
| Test relevant commentary and tool-loop behavior. | no | unknown | not applicable | [ ] | No assistant history or output-item replay is sent: this application extracts one strict metadata object per independent request. |

## Context Compaction

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess native compaction for long-running conversations and tool-heavy workflows. | no | unknown | not applicable | [ ] | No growing conversation exists. Optional extraction input is bounded (8000 tokens default); compaction would add unnecessary retained state and complexity. |
| Confirm changes to compaction strategy with the developer. | no | unknown | not applicable | [ ] | No growing conversation exists. Optional extraction input is bounded (8000 tokens default); compaction would add unnecessary retained state and complexity. |
| Configure appropriate in-request or standalone compaction and thresholds. | no | unknown | not applicable | [ ] | No growing conversation exists. Optional extraction input is bounded (8000 tokens default); compaction would add unnecessary retained state and complexity. |
| Preserve encrypted compaction items during manual state management. | no | unknown | not applicable | [ ] | No growing conversation exists. Optional extraction input is bounded (8000 tokens default); compaction would add unnecessary retained state and complexity. |
| Verify privacy requirements and model or provider compatibility. | no | unknown | not applicable | [ ] | No growing conversation exists. Optional extraction input is bounded (8000 tokens default); compaction would add unnecessary retained state and complexity. |

## Structured Outputs

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve required structured-output schemas, validation, parsing, and error handling. | yes | yes | implemented | [x] | Optional Responses route uses a strict document metadata JSON schema and Pydantic validation, bounded output, refusal/empty/incomplete failure handling. tests/unit/test_models.py. |
| Verify model and provider compatibility and add focused schema tests. | yes | yes | implemented | [x] | Optional Responses route uses a strict document metadata JSON schema and Pydantic validation, bounded output, refusal/empty/incomplete failure handling. tests/unit/test_models.py. |
| Avoid imposing structured outputs on unrestricted-text workflows. | yes | yes | implemented | [x] | Optional Responses route uses a strict document metadata JSON schema and Pydantic validation, bounded output, refusal/empty/incomplete failure handling. tests/unit/test_models.py. |

## Tools

### Tool Choice

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Preserve automatic, required, or restricted tool-selection behavior. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Confirm meaningful changes to tool-use policy with the developer. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |

### Tool Search and Additional Tools

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess deferred tool discovery for large or dynamic tool catalogs. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Preserve correctly positioned additional-tool items and append-only replay. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Maintain stable cached prefixes without unnecessary tool-search complexity. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Confirm adoption or higher-lift implementation with the developer. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |

### Parallel Tool Calls

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess concurrent execution of independent tools. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Preserve execution order, shared-state assumptions, approvals, and side-effect controls. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Confirm behavior-changing concurrency with the developer. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |

### Programmatic Tool Calling

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess supported programmatic coordination of tool calls. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Verify model, provider, SDK, tool, and execution-environment support. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Preserve permissions, approvals, side-effect controls, and application behavior. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Distinguish programmatic calling from ordinary sequential or parallel function calling. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Test execution, results, failures, and changed approval behavior. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |

### Model-Aligned Tool Interfaces

| Guidance item | Applicable | Supported | Decision | Implemented | Rationale or evidence |
|---|---|---|---|---|---|
| Assess conventional repository-search, patch-oriented editing, or other model-aligned tool interfaces. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |
| Confirm higher-lift tool redesign with the developer before implementation. | no | unknown | not applicable | [ ] | No model tools, dynamic catalogs, code execution or tool side effects exist in this ingestion/metadata application. Azure Durable activity concurrency is infrastructure execution, not model tool calling. |

## Outcome

**Implemented or already present:** All five approved capability stages have code, configuration, tests, and documentation; optional model/service routes are available but not activated.
**Remaining work:** Live-Azure acceptance, private-network smoke tests, notification delivery, supported region/quota checks, actual-corpus quality/latency/cost comparisons, and tenant-specific retention/residency sign-off. No deployed SLA, quality improvement or live cost saving is claimed.
**Developer decisions requiring follow-up:** Production Entra app/roles and scope mapping; compatible region and quota; retention/residency/ZDR requirements; optional model deployments, analyzer dependencies, paid capacity and approved operating objectives. Defaults avoid enabling new generative deployments or preview features.
**Validation evidence:** See docs/validation.md. Mocked suite, SDK request contract checks, Python lint/format, Bicep compilation/profile parameters and compiled infrastructure invariants are local checks. Live Azure integration remains unrun.
