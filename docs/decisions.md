# Engineer decision worksheet
Do not treat the starter values as the only correct design. Record alternatives, evidence, trade-offs, rollback and a review date.

| Decision you own | Current starting point | Questions to resolve |
|---|---|---|
| Approval policy | Above $500; different approver | Is the threshold per order, user, day or budget owner? |
| Credit exposure | Commit at checkout; release on settlement | What if the customer disputes an invoice? |
| Reservation deadline | 30 minutes before invoicing | What is the real approval lead time? Does expiration need escalation? |
| Payment terms | Net 14, shipment before payment allowed | Which customers can ship on credit? |
| Returns | Full paid/delivered orders only | Are partial returns, damages and restocking fees required? |
| Isolation | Company-scoped application queries | When should PostgreSQL RLS or separate databases be introduced? |
| Worker transport | PostgreSQL outbox | What measured queue depth/latency would justify a broker? |
| Lock granularity | Company row serializes mutations | What throughput is required for the largest tenant? |
| Deployment | One codebase, web + worker processes | What evidence justifies extracting a service? |
| SLO / error budget | Proposed in business.md | How will customer success be measured? |
| Cost | Local first, ephemeral cloud labs later | What monthly ceiling and shutdown deadline can you approve? |
| Recovery | Local rehearsal; RDS targets proposed | What business data loss is acceptable and who declares recovery? |

First assignment: choose the reservation deadline policy. Explain a customer failure case caused by the current default and propose a measurable replacement. Do not change it until you have completed Gate B1 and written acceptance tests for the new behavior.
