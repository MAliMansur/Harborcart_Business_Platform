# Production readiness review — currently NOT approved
This repository is a functioning local business application and a phased engineering lab. It is not ready for public customer traffic merely because tests pass.

Record an owner, evidence link, review date and status for each gate:
- [ ] Current patched Python and reviewed Gunicorn pin; dependency lock and vulnerability audit.
- [ ] PostgreSQL suite including all three concurrency tests, with actual output.
- [ ] Real browser journey and responsive/accessibility checks in supported browsers.
- [ ] Container build, image digest, image vulnerability scan, SBOM and provenance.
- [ ] PostgreSQL role separation, TLS certificate verification and connection limits.
- [ ] Identity provisioning/deprovisioning, password reset, privileged MFA/SSO decision and abuse controls.
- [ ] Threat model: tenant isolation, authorization, CSRF, input boundaries, secret handling and data retention.
- [ ] Migration rehearsal, backward compatibility and observed rollback.
- [ ] Valid load model, measured bottlenecks, agreed capacity and SLO instrumentation.
- [ ] Alert delivery to an approved on-call destination; alert test; independent monitoring of the monitoring stack.
- [ ] Backups, isolated PostgreSQL/RDS restore, business reconciliation and measured RPO/RTO.
- [ ] AWS account/region, cost model, explicit spending approval and reviewed Terraform plan.
- [ ] EKS/Helm configuration, network policy, private data services, TLS ingress and secrets.
- [ ] Argo CD promotion/RBAC, immutable artifact references and drift handling.
- [ ] Protected branches, required CI, environment reviewers and prevention of self-approval.
- [ ] Incident ownership, runbooks, communication plan, recovery/rollback authority and postmortem.
- [ ] Safe teardown plan and retention decisions.

Known scope limits: no real payment/carrier/email integration, partial fulfillment/refunds, taxation, inventory purchasing, enterprise identity lifecycle, RLS, tamper-evident audit storage or completed public deployment. No availability, throughput or latency target has been measured or achieved yet.

The release-review workflow records a candidate approval gate only. It does not deploy, validate every evidence claim or create repository protection settings. Verify those settings explicitly; an environment without required reviewers is not an approval control.
