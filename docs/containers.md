# Gate B2: PostgreSQL and containers

Business scenario: the team needs a repeatable runtime that supports more than one web process and reliable concurrent stock reservations.

Prerequisites: Gate B1 evidence; Docker Engine/Desktop with Compose v2 available in WSL; sufficient free memory/disk; internet access for image pulls. The supplied runtime budget is roughly 2–3 GiB across enabled services, before Docker/OS overhead. Measure actual use with docker stats.

## Start and verify
Stop the host web and worker processes using Ctrl-C. From the repository:
```bash
source .venv/bin/activate
make bootstrap
docker version
docker compose version
docker compose config --quiet
make compose-up
docker compose ps
docker compose logs --tail=80 migrate web worker
make compose-seed
make test-postgres
docker compose exec -T web python manage.py reconcile
curl --fail http://localhost:8080/readyz
```

Expected: db healthy; migrate exited 0; web and worker healthy; the test run executes the three PostgreSQL race tests without skipping; reconciliation passed true. These are expected outputs for you to verify, not recorded results from this delivery.

Application and worker run as UID 10001 with a read-only root filesystem, dropped Linux capabilities and writable /tmp only. PostgreSQL has a named persistent volume. Web uses the non-superuser hc_app role; migrations use hc_owner. hc_test has CREATEDB for isolated test databases and is local-lab only. Remove test credentials/role from a future production deployment.

The app is not granted schema ownership. Init scripts configure default privileges so future tables and sequences created by the migration owner are usable by the runtime. They run only for a newly initialized PostgreSQL volume; changing an init script does not update an existing volume.

## Monitoring
```bash
make observe
docker compose ps
docker compose exec -T web python manage.py worker_health --name worker-1
```
Open Prometheus /targets and /alerts on localhost:9090. HarborCart and Prometheus scrape targets should be UP. Open Grafana on localhost:3000 and select HarborCart → Business operations.

The dashboard uses database-derived metrics: order counts by state, outbox state, queue age, worker heartbeat age, scrape status and low-stock records. It is not populated by invented time-series data. No external paging receiver is configured. An independent alert delivery path and monitoring of Prometheus itself are later readiness requirements.

Metric authentication uses .local/metrics-token. If you rotate METRICS_TOKEN, update that private token file too and restart the relevant containers; never paste the token into evidence.

## Common faults
- Port 8080 in use: stop the earlier host server; do not kill an unidentified process.
- Database password changed in .env after initialization: existing PostgreSQL roles keep their old passwords. Plan an explicit rotation; do not delete the volume to hide the problem.
- Image tag unavailable: verify official release/image availability and record a reviewed pin update. Do not silently use latest.
- Permission denied in PostgreSQL: inspect current_user, schema privileges and the migration owner. Do not grant runtime SUPERUSER.
- Repeated unhealthy worker: inspect its logs and queue state before increasing healthcheck thresholds.
- HTTP healthy but invoice queue increasing: follow the queue runbook.

## Safe stop
```bash
docker compose --profile observability down
docker volume ls --filter name=harborcart-business
```
The stop command retains volumes. This project does not include a volume deletion target. Deleting a database volume is a separate destructive operation requiring your explicit decision and recovery evidence. Do not run a generic docker system prune on a shared workstation.

Completion gate: three PostgreSQL race tests run; real browser journey passes on PostgreSQL; runtime role cannot create/drop schema; persistence survives container recreation; monitoring shows actual business activity; a worker interruption is recovered without duplicated invoices.
