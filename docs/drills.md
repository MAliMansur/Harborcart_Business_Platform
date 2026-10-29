# Incident exercises — investigation first

Keep the root-cause file closed until you have written hypotheses and supporting evidence. Never run these on a public system or real customer data. The HC-01 helper refuses production mode and acts only on fictional demo records.

For every drill: record impact, start time, last known healthy state, hypotheses, commands and observations, the smallest corrective change, rollback and recovery proof. Use the incident and postmortem templates in evidence/templates/.

## HC-01: checkout accepted, fulfillment stalled
Business impact: a branch's purchase is accepted but its invoice never arrives. The browser and /healthz still work.

Prerequisites: B1 passed, demo seeded, buyer cart empty, web and worker running. Prepare one new exercise purchase:
```bash
python manage.py lab_scenario prepare
```
Save the returned order UUID. Allow the worker to attempt processing; inspect the purchase and Operations center. Do not edit database rows just to advance the status.

Investigate:
```bash
curl --fail http://localhost:8080/healthz
curl --fail http://localhost:8080/readyz
python manage.py worker_health --name worker-1
python manage.py shell -c 'from commerce.models import OutboxEvent; print(list(OutboxEvent.objects.exclude(status="done").values("id","order_id","kind","status","attempts","last_error","available_at")))'
make reconcile
```
Use the worker terminal's structured logs and the exact affected order. Compare the queue state to a successfully processed purchase. Explain whether the fault is capacity, database connectivity, authorization, schema compatibility or message handling.

Before opening solutions, submit three hypotheses, one rejected hypothesis with evidence, and the invariant you will check after recovery.

Completion: affected order confirmed, exactly one invoice, failed job completed, reconciliation passes, timeline recorded. A successful replay alone is insufficient.

## HC-02: worker capacity loss
Facilitator only: stop the local worker terminal with Ctrl-C, then have a buyer submit a new below-threshold purchase. An investigator should receive only the symptom: accepted orders no longer become confirmed.

Investigate age of oldest pending job, heartbeat age, worker process/log state and web/database readiness. Record what remains available and what is degraded. Recover within the reservation deadline; explain what should happen if that deadline is exceeded.

## HC-03: inventory conflict
Two buyers request the last unit of the same SKU from the same warehouse. Before injecting this in the UI, run the PostgreSQL concurrency suite at Gate B2.
Expected business policy: one purchase succeeds; the other receives a conflict without a partial reservation or credit charge. Demonstrate the rejected transaction and ledger reconciliation. SQLite evidence is not sufficient for this concurrency claim.

## HC-04: apparent payment duplication
A finance user sees a timeout after submitting a payment reference and retries. Investigate invoice, payment reference, credit exposure and audit records. Prove whether there was one settlement or two. The same reference must be safe to repeat; a different reference on the paid invoice must conflict. This lab records payments locally; no payment provider is involved.

## HC-05: monitoring blind spot
After B2, have a facilitator introduce a mismatch between the application's metrics token and Prometheus's mounted token in a separate local exercise environment. Give the investigator only: the application works but dashboards stopped updating.
Investigate /targets, scrape errors, up, absent-series behavior and token file access. Do not disable authentication to recover observability. Avoid printing the token in logs/evidence.

## HC-06: database interruption
After B2 and a verified backup, stop only the local db service in a controlled exercise. Explain expected differences among liveness, readiness, authenticated page requests, metrics and worker retries. Recover the database, check persistence and reconciliation, then repeat the exact affected business request using its original idempotency key.

## Future controlled drills
Kubernetes CrashLoopBackOff, failed rollout, resource exhaustion, service discovery/DNS and NetworkPolicy faults belong to the local cluster phase. Terraform state locks and IAM denials belong to the infrastructure phase with explicit cost approval. RDS recovery and region failure require an isolated restored target and a time-bounded approved plan.

Do not invent a production incident outcome from reading a runbook. Mark preparation, execution and recovery separately.
