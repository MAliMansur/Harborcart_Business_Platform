# Runbook: database unavailable or permission denied
Scope: local PostgreSQL profile. RDS procedures must be completed for the approved cloud topology before deployment.

Investigate before altering credentials or roles:
```bash
docker compose ps db migrate web worker
docker compose logs --tail=100 db migrate worker
docker compose exec -T db pg_isready -U hc_owner -d harborcart
docker compose exec -T db psql -U hc_owner -d harborcart -c "SELECT pid, usename, state, wait_event_type, wait_event FROM pg_stat_activity;"
docker compose exec -T db psql -U hc_owner -d harborcart -c "\\du"
curl --fail http://localhost:8080/readyz
```
Do not include connection strings/passwords in evidence. Distinguish connection refusal, DNS failure, invalid password, certificate verification, exhausted connections, lock timeout, missing migration and insufficient table privileges.

Correct only the diagnosed fault. A password change in an environment file does not rotate an existing PostgreSQL role. Init scripts run only on first initialization. Runtime role hc_app must remain non-superuser. Migrations use hc_owner; future production requires a restricted migration identity too.

Recovery checks: database responds; schema matches reviewed migration; runtime can read and mutate allowed tables; runtime cannot create/drop schema; affected idempotent requests are safely replayed; reconciliation passes. Investigate blocking queries before terminating any session; termination is a separate change decision.
