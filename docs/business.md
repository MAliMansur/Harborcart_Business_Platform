# Business requirements and acceptance rules

## Scenario
HarborCart supports corporate equipment procurement. Each company is a separate buyer workspace with its own contract catalog, warehouses, credit facility and staff. Atlas Supply and Boreal Trading are fictional tenants. Tenant isolation is enforced in application queries and service operations; PostgreSQL row-level security is a future defense-in-depth decision.

The operator account is a workspace administrator, not a global cross-company administrator. The worker is a trusted internal process that serves all companies.

## Working capabilities
| Domain | Implemented behavior | Operational concern |
|---|---|---|
| Identity | Password login, session expiry, five roles, login throttling, CSRF | Cookie security, account lifecycle, malicious login attempts |
| Catalog | Search/filter, active products, contract discounts | Price changes and stale carts |
| Procurement | Persisted carts, version checks, idempotency keys | Duplicate/retried submissions |
| Credit | Commit at checkout; release on payment or unpaid cancellation | Overcommitment, reconciliation |
| Approval | Above-threshold purchases need a different approver | Segregation of duties, delayed approvals |
| Inventory | Per-warehouse stock, reservation, adjustment reasons | Overselling, reservation leaks |
| Fulfillment | Invoice confirmation, packing, shipping, delivery | Invalid transitions and worker dependency |
| Finance | Immutable payment/refund records with unique references | Duplicate settlement, audit evidence |
| Returns | Paid + delivered only; receive goods before refund | Double restocking, refund timing |
| Background work | Transactional outbox, leases, backoff, dead letters, replay | Crashes, stale ownership, poison jobs |
| Operations | Health/readiness, authenticated metrics, structured request logs | Silent backlog, monitoring failures |
| Recovery | SQLite restore rehearsal and read-only reconciliation | Backup integrity versus actual recovery |

## State rules
- Prices are USD integer cents; discounts use basis points and half-up integer rounding. No floating-point currency arithmetic.
- Shipping and tax are not charged in this release. Totals represent merchandise only.
- Checkout reserves stock only in the selected warehouse and verifies credit in the same transaction.
- Orders above $500 in Atlas's demo policy require approval; exactly $500 does not.
- Stock and credit remain committed during approval. The 30-minute deadline applies until invoicing confirms the order. Confirmed orders retain reservations until shipping or unpaid cancellation.
- Payment may be recorded before or after delivery. A paid order cannot use cancellation; a return requires delivery.
- Full returns only. Partial shipments, split fulfillment, partial payments and partial refunds need additional accounting states and are not implemented.
- Checkout replay with the same key and identical request returns the original order. A changed body with the same key returns 409.
- Repeating shipment at the same current state, recording the same payment reference, or refunding the same reference has no duplicate effect.
- A warehouse operator cannot approve or settle purchases. A buyer cannot see another buyer's order. Other roles can see company orders according to their responsibility.
- A foreign company's resource returns 404 rather than exposing its existence.
- Audit rows have no mutation endpoint. A database administrator could still alter them; this is not a tamper-evident compliance ledger.

## Proposed targets — NOT measured achievements
Before AWS deployment, approve or replace these working targets: 99.9% successful valid checkout requests over 30 days; p95 checkout latency below 750 ms at an agreed workload; 99% of accepted jobs completed within 60 seconds; RPO 15 minutes and RTO 60 minutes for the later production database. Define exactly which outcomes and exclusions count before collecting measurements.

The current business gauges cannot calculate the checkout availability or latency SLO. Add HTTP counters/histograms or an ingress/OpenTelemetry source in the observability phase. Do not infer an SLO from current order counts.

## Your decisions
Complete docs/decisions.md. Explain who owns credit exposure, whether the 30-minute deadline fits real approvals, whether payment must precede dispatch, and which return policy a real business would require. Change one rule through a branch, tests, review notes and rollback evidence after the first gate.
