# HarborCart Business
A working B2B procurement, inventory, fulfillment and finance application for a hands-on DevOps / SRE engineering lab.

**Status:** local application foundation, version 0.2.0. This is a fictional personal project, not a deployed commercial service. Read [verification evidence](evidence/VERIFICATION.md) before making claims about it.

## What the business does
Atlas Supply buys equipment for branch offices on a contract account. Buyers request goods, purchasing managers approve larger commitments, warehouse operators dispatch them, and finance records invoice settlement. Returns cross the warehouse and finance boundaries again.

The app includes two isolated companies, five roles, 17 seeded products across six categories, multi-warehouse stock, contract discounts, credit limits, a persistent cart, idempotent checkout, purchasing approvals, expiring reservations, invoices, shipments, payments, returns, refunds, notifications, audit history and a durable background queue.

This release records full payments and full refunds in a sandbox ledger. It does not connect to a bank, email provider, tax service or carrier. See [business scope](docs/business.md).

## Start locally — no Docker or AWS required
Extract this archive into its own **harborcart-business** folder. Keep the earlier Phase 1 folder as your previous milestone. Do not copy its virtual environment or database over this project.

From the new repository root, using your Python 3.12 interpreter:
```bash
python3 --version
python3 scripts/preflight.py
python3 -m venv .venv
source .venv/bin/activate
make bootstrap
make install
make setup
make check
make test
cat .local/demo-credentials.txt
make run
```

Open **http://localhost:8080**. In a second terminal, from the same folder:
```bash
source .venv/bin/activate
make worker
```

Use the generated password with these usernames:

| Username | Responsibility |
|---|---|
| buyer | Build a purchase, submit it, request a return |
| manager | Review and approve another person's purchase |
| warehouse | Adjust stock, pack, ship, receive returned goods |
| finance | Record invoice payment and refund references |
| operator | Inspect all workspace functions, jobs and audit records |
| rival / rival-manager | Check isolation in the Boreal Trading workspace |

The app does not print the generated password in setup logs. Do not commit or share `.env` or `.local/`. Restarting or rerunning `make setup` preserves existing demo data. Reservations in pending/queued orders expire after 30 minutes, so submit a new purchase if the seeded ones have expired.

Your Python **3.12.15** passes this project's branch check. Missing **unzip** no longer blocks execution after extraction. Patch maintenance is a separate release gate; use a currently patched supported interpreter before public deployment. Python 3.12–3.14 is accepted; this delivery was executed on 3.12.14.

## First business verification gate
Follow [the hands-on walkthrough](docs/first-gate.md), which includes expected behavior, evidence to collect and a troubleshooting interview. Complete it before moving to containers or AWS.

The first transaction to try: buy **four Managed network switches** from EAST. The seeded contract price is $179.55 each; the $718.20 total requires approval because it exceeds $500. Sign in as manager, approve it, let the worker invoice it, and continue as warehouse and finance. These are scenario inputs, not performance metrics.

Useful commands:
```bash
make reconcile
make recovery
python scripts/smoke_http.py
python manage.py worker --drain
python manage.py worker_health --name worker-1
```

`smoke_http.py` creates its own temporary database and loopback Gunicorn server, drives the complete order-to-refund lifecycle with cookie sessions and CSRF, then removes that temporary database. It does not mutate your normal workspace.

## Why this needs operations engineering
The web process and worker fail independently. A successful checkout commits stock and credit plus a durable job in one transaction; an unavailable worker leaves a visible backlog. Replays must not duplicate invoices or settlements. Database outages affect authenticated traffic, metrics and workers. A faulty release can violate financial or stock invariants even when an HTTP health check is green.

Start with one application codebase and two deployable process types. Split services only after measuring a reason to accept distributed transactions, additional deployment units and more failure modes. Read the [architecture decisions](docs/architecture.md).

## PostgreSQL and observability — later local gate
After the first gate and installing Docker Engine / Docker Desktop with Compose v2:
```bash
# Stop the host runserver and worker with Ctrl-C first.
make compose-up
make compose-seed
make test-postgres
make observe
docker compose ps
```
This creates a **separate PostgreSQL demo database**; it does not import your SQLite data. Web: http://localhost:8080. Prometheus: http://localhost:9090. Grafana: http://localhost:3000, username `operator`, password from `GRAFANA_PASSWORD` in your private `.env`.

Read [container operations](docs/containers.md) first. These container profiles and GitHub workflows are supplied for your next verification gate; they were not executed here. PostgreSQL, Prometheus and Grafana image pulls must be verified on your machine.

Stop containers while keeping their volumes:
```bash
make compose-down
```
There is no automatic volume deletion or AWS creation target.

## Repository map
| Path | Purpose |
|---|---|
| commerce/models.py, migrations/ | Domain schema and database constraints |
| commerce/services.py | Authorized transactional business operations |
| commerce/worker.py | Durable claims, ownership tokens, retries and effects |
| commerce/views.py, templates/, static/ | Browser workspace and authenticated JSON operations |
| commerce/tests/ | Business, authorization, worker and PostgreSQL race tests |
| harbor/ | Environment validation, Django settings, routes |
| scripts/ | Bootstrap, preflight, isolated HTTP exercise, repository guard |
| Dockerfile, compose.yaml | Web, worker, migration job and local PostgreSQL runtime |
| ops/ | Database roles, Prometheus alerts, Grafana dashboards |
| .github/ | CI, review gate, dependency updates, PR template |
| docs/ | Requirements, architecture, walkthrough, runbooks and roadmap |
| evidence/ | What was executed, what remains unverified, learner templates |

## Engineering gates
The [12-phase roadmap](docs/roadmap.md) retains Linux, Git, Docker, GitHub Actions, Terraform, EKS, Kubernetes, Helm, Argo CD, observability, recovery and portfolio outcomes. This upgrade gives those phases a substantial application to operate. It does not mark infrastructure phases complete.

No AWS resources were provisioned, no GitHub repository was published, and no deployment approval was assumed. Future paid infrastructure requires an explicit budget and approval of a concrete Terraform plan.

Before a public release: verify PostgreSQL races and recovery; close current runtime/version exceptions; scan and pin image digests; configure protected branches and required production reviewers; add TLS, secret management, identity lifecycle, independent alert delivery, load evidence and an approved threat model. See [production readiness](docs/production-readiness.md).
