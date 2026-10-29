# Security policy and scope
Use fictional data and loopback access for the supplied local profile. Do not expose it publicly until the production readiness review passes.

Implemented: Django password hashing and sessions, CSRF, role checks in business services, tenant-scoped resource lookup, hidden foreign-resource responses, integer money, server-side pricing, stock/credit constraints, idempotency, structured request logging, protected metrics, generated local secrets and an unprivileged application container configuration.

Local limitations: no MFA/SSO or password-reset workflow; login throttling is application/database based; audit rows are not tamper-evident; PostgreSQL RLS is not enabled; the demo shares one generated password among fictional accounts; internal Compose traffic is not TLS encrypted. Demo mode and SQLite are rejected in production settings.

Never commit .env, .local, credentials, cookies, database dumps or Terraform state. The repository guard is intentionally modest; run a maintained secret scanner and platform secret scanning before publishing. No real credentials are included in the archive.

Run:
```bash
python -m pip install --require-hashes -r requirements-security.lock
bandit -r commerce harbor scripts -x commerce/tests,harbor/settings_test.py -c bandit.toml
pip-audit --require-hashes -r requirements.lock
python scripts/check_repository.py
```
Bandit exceptions are narrowly annotated for fixed subprocess arguments and fixed recovery queries. Review them when changing those paths. A clean scan is evidence about the tool's checks at that time, not a guarantee that no vulnerability exists.

For a future published repository, configure a private vulnerability-reporting channel and document an owner/response process. Do not place live secrets or an exploitable customer-data example in a public issue.
