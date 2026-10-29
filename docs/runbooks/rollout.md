# Runbook: failed release and rollback
Current local gate: application changes plus migrations. Kubernetes/Argo-specific procedures will be implemented with that phase's real manifests.

Before a release, record commit, dependency lock hash, image digest when available, schema compatibility, test evidence, customer-facing smoke checks and rollback candidate. Ensure the previous version can run against the expanded schema.

If failures appear:
1. Stop promotion. Record the exact artifact and first failing business operation.
2. Compare liveness, readiness, logs, queue age and business results. A green process probe is insufficient.
3. Distinguish bad configuration, missing migration, changed event contract, role privilege error, resource pressure and defective application code.
4. Restore the last compatible application/configuration artifact. Preserve committed business data.
5. Verify new purchases, a previously affected purchase, background processing, invoice uniqueness and reconciliation.
6. Document whether a forward database fix or data repair is required. Never automatically reverse a destructive migration.

For local Compose, rebuild from the reviewed commit and rerun the migration job only after understanding compatibility. A container recreate does not restore database state. Always record rollback results rather than assuming that checking out an older commit restored service.
