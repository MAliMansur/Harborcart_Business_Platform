# Runbook: delayed invoices or background work
Trigger: orders remain queued, queue age exceeds the agreed threshold, worker heartbeat is stale, or dead letters appear.

1. Record affected order IDs, time window and customer impact. Separate new submissions from approved/queued/confirmed purchases.
2. Check web liveness and database readiness. Check the worker's last heartbeat and logs.
3. Inspect event kind, status, attempts, available_at, lease_until and last_error. Use only the tenant-scoped UI unless acting as the trusted platform operator.
4. Distinguish absent worker, database failure, insufficient throughput, unsupported event type and repeated handler error.
5. Preserve evidence before replay. A retry budget limits damage; it is not a repair.
6. Correct the actual cause. Restart the worker for a process failure; fix/revert the incompatible handler or producer for a release failure.
7. Replay only the affected retry/dead job as operator. Do not bulk set all jobs to pending.
8. Verify status progression, one invoice per order, consistent stock/credit and a shrinking queue. Check new transactions as well as the original incident.

Commands for the local process:
```bash
python manage.py worker_health --name worker-1
python manage.py shell -c 'from commerce.models import OutboxEvent; print(list(OutboxEvent.objects.exclude(status="done").values("id","order_id","kind","status","attempts","last_error","lease_until","available_at")[:30]))'
make reconcile
```
Compose equivalents:
```bash
docker compose ps worker db
docker compose logs --tail=100 worker
docker compose exec -T worker python manage.py worker_health --name worker-1
docker compose exec -T web python manage.py reconcile
```
Rollback: revert a faulty code release to a schema-compatible image; keep committed orders and events. Do not roll back database data by deleting jobs. Prevention: compatibility tests, worker supervision, queue-age alerts and business reconciliation.
