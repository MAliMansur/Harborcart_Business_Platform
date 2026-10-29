# Executed verification and explicit limits

Verification completed in the assistant's isolated Linux workspace, not on your Windows/WSL machine. Last end-to-end run: 2026-10-27 (timestamps in the attached JSON are UTC). Source supplied for your own execution and review.

## Passed
| Check | Observed result | Evidence |
|---|---|---|
| Django checks | No system-check issues; no model changes missing migrations | check output during build |
| Automated suite | 62 discovered; 59 passed; 3 PostgreSQL concurrency tests skipped | tests.txt |
| Real HTTP business journey | Cookie login for six users; purchase, approval, worker invoice, dispatch, delivery, payment, return, receipt and refund completed | http-smoke.json |
| Replay/isolation/security | Checkout replay reused one order; foreign order 404; role 403; CSRF-protected requests; protected metrics; escaped product input | tests.txt and http-smoke.json |
| HTTP pages/static assets | Eleven workspace pages served; CSS retrieved from the actual Gunicorn server | http-smoke.json |
| Controlled HC-01 recovery | Handler attempt failed; compatibility repair + authorized replay completed; order confirmed | http-smoke.json |
| Reconciliation | Stock reservations, credit commitments, invoice/payment/refund relationships passed; deliberate credit drift detected by test | tests.txt and http-smoke.json |
| Local SQLite recovery | Backup restored to a separate file; integrity ok; zero foreign-key violations; critical table counts matched; restored business reconciliation passed | http-smoke.json |
| Source scan | Bandit reported zero remaining findings after narrowly documented fixed-command/query reviews | bandit.json |
| Dependency audit | pip-audit reported no known vulnerabilities in the nine locked runtime dependencies at execution time | pip-audit.json |
| Static configuration checks | YAML/JSON parsed; JavaScript syntax checked; database init shell syntax checked; git whitespace and tracked-file checks passed | build checks; these are NOT runtime container validation |

The local recovery rehearsal restored 12 fictional orders, 11 invoices and 33 stock records from the isolated HTTP exercise. These are observed fixture counts, not customer volume or performance results. The actual temporary database and generated credentials are deliberately excluded from this archive.

## Not executed / not proven
- PostgreSQL row-lock behavior and the three concurrency tests. Docker and PostgreSQL were unavailable in this workspace; SQLite results do not establish PostgreSQL correctness.
- Container builds/image pulls, Compose startup, runtime database privileges and resource limits.
- Prometheus configuration/rule validation with promtool, actual scraping/alert delivery, or Grafana dashboard rendering.
- A real browser's JavaScript interactions, responsive layout and accessibility behavior. Chromium download attempts failed; HTTP and template tests are not browser automation.
- GitHub Actions execution, protected branch/environment settings, image scanning/SBOM/provenance or deployment approvals.
- Terraform, EKS, Helm, Argo CD, RDS, AWS disaster recovery or cloud cost measurements. Those remain later implementation phases.
- Load/soak tests, p95 latency, throughput, achieved availability, RPO or RTO. Proposed targets are not measured results.
- Any execution on your computer or a commercial production system.

## Runtime caveats
Executed Python: 3.12.14. The supplied local preflight accepts your 3.12.15. A fully patched interpreter remains required before public deployment. Gunicorn 26.2.0 was installed and tested; the official release source lists 26.2.2, unavailable from the package index used here. Review/update that pin before a public release. See versions-and-sources.md.

## What was fixed while building
Initial tests exposed a workspace context/template naming mismatch; it was corrected and the affected tests passed. The extended incident HTTP harness initially supplied an unhyphenated SQLite UUID to a URL requiring standard UUID formatting; the harness was corrected and the full journey then passed. These were development findings, not claimed production incidents.

No AWS resources were created. No real payment, carrier or email service was called. No GitHub repository or message was published. Your earlier local Phase 1 directory was not modified by this build.
