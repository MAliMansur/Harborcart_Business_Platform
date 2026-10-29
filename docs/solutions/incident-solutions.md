# Incident solutions — open after investigation
This file contains spoilers. Keep your initial incident notes; compare them with the actual cause.

## HC-01
The facilitator creates an order with an outbox event kind from an unsupported older event contract: order.accepted.v0. The current worker does not handle that kind. Attempts raise ValueError, are retried with bounded backoff and ultimately become dead letters. The order and stock/credit commitments are real demo records, not fake dashboard values.

Corrective action after identifying the order UUID:
```bash
python manage.py lab_scenario repair --order YOUR-RECORDED-UUID
```
The helper restricts repair to that exercise's queued purchase, restores the understood contract and records an audit event. Sign in as operator, inspect the failed job and choose Replay job. Keep the normal worker running, refresh the order, and verify exactly one invoice plus reconciliation:
```bash
make reconcile
```
If more than 30 minutes elapsed, the worker may have cancelled the order and released its reservations. Do not resurrect a cancelled purchase by changing its status. Prepare a new exercise and document the expiration outcome.

Prevention: backward-compatible event schemas, contract tests across producer/consumer releases, explicit version handling, dead-letter alerts and rolling-deployment compatibility. A replay without a compatibility fix repeats the fault.

## HC-02
The worker is absent; the web and database remain live. Restart only the worker after checking why it stopped. Watch queue age drain and verify invoices are not duplicated. If reservations expired, validate cancelled orders and released credit/stock instead of forcing confirmation. Prevention includes worker health, queue-age alerts, process supervision and measured worker capacity.

## HC-03
Stock availability is a transactional invariant. In PostgreSQL the company lock serializes these commits, stock rows are locked, and a database constraint prevents reserved stock exceeding on-hand stock. A read outside the transaction is only a hint, not authority to sell. The losing checkout must leave its cart intact and create no partial order/event/credit mutation. Use the PostgreSQL race tests and inspect outcomes.

## HC-04
Checkout idempotency, unique payment references and the one-payment-per-invoice relationship protect repeated recording. Reuse the exact reference after an ambiguous result. Never assume a timeout means failure. For future real providers, reconcile provider status and use its idempotency protocol; the local guarantees cannot prove external settlement semantics.

## HC-05
A bearer-token mismatch returns 401 to the metrics collector. Correct the authenticated configuration, verify file permissions and restart/reload the affected collector as needed. Prove up=1, fresh business series and alert recovery. Prevention: coordinated secret rotation, scrape-failure alerts, absent-series alerts and an independent monitoring heartbeat. Never remove authentication.

## HC-06
The database is unavailable. /healthz can remain 200 because the process is alive; /readyz returns 503; business operations fail; the worker logs connection failures and retries. Restore connectivity, inspect database health and schema, validate expected counts and reconciliation, then use safe request replays. Do not delete the persistent volume or run migrations blindly.
