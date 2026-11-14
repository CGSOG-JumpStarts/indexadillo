# Using Indexadillo v2

The implementation, API examples and operational guidance are maintained in:

* [README](README.md): architecture, local checks and API overview.
* [Deployment and identity](docs/deployment.md): Entra roles, scopes, Azure profiles,
  networking and optional model routes.
* [Operations](docs/operations.md): document lifecycle, limits, retention,
  monitoring and recovery.
* [Evaluation](docs/evaluation.md): labeled retrieval/model comparisons and
  isolated Durable Task Scheduler benchmarks.
* [Migration and rollback](docs/migration.md): v1 compatibility changes, index
  aliases and optional GA knowledge-source binding.

This release requires authentication and explicit tenant routing. Old unauthenticated
integration examples and the previous plain-text indexing response do not apply.
