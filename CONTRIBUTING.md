# Working on HarborCart
Create a branch for one business or operational change. Write the acceptance rule first. Prefer a targeted test for an actual business failure over a test that merely repeats the implementation.

Before a PR:
```bash
make check
make test
python scripts/smoke_http.py
make reconcile
git diff --check
```
Run PostgreSQL tests for transaction/locking/schema changes. Run container, dependency and image checks when their inputs change. Do not merge until the appropriate evidence is available.

Use the PR template. Explain the observed problem, resulting behavior, technical trade-offs and rollback. Avoid adding Kubernetes resources or additional services without a measured need or a specific learning goal.

Publish portfolio claims only after you personally execute and understand the relevant work. Suggested wording: “Built and operated a personal B2B commerce lab; implemented and tested [specific verified capabilities].” Keep separate sections for supplied implementation, your executed evidence and future work. Never describe fictional demo companies or drills as client employment.
