# Cost-conscious implementation and teardown

Current authorized cloud spend: **none**. The delivered local app, tests and documentation require no AWS API calls. GitHub-hosted automation may consume your account's included minutes/storage; check account limits before enabling it. No hosted workflow has been triggered here.

Start with local Python/SQLite, then local Docker/PostgreSQL, then a local Kubernetes cluster. Keep observability optional and bounded: Prometheus retains three days / 512 MB in the supplied profile. Stop local containers between sessions.

Before any AWS apply, record:
- account/environment, region, resource inventory and owner;
- explicit monthly and per-session budget ceilings chosen by you;
- an estimate from current official AWS pricing or the AWS Pricing Calculator;
- expected lifetime, scheduled shutdown and teardown owner;
- EKS control plane, worker compute, EBS, RDS, load balancer, NAT/egress, public IPv4, logs, backups, ECR and data-transfer costs;
- tags for project, environment, owner, expiry and cost center;
- budget alert thresholds and an independent manual cost check;
- the exact reviewed Terraform plan and what may be destroyed during teardown.

Budget alerts are notifications, not a guaranteed hard spending cap. Do not assume a stopped application removes control-plane, storage, networking or backup costs.

Local shutdown: Ctrl-C for your web/worker terminals; make compose-down for containers. Volumes remain. Do not delete any database, backup or volume until you explicitly authorize that deletion after recovery evidence is checked.

Cloud teardown, when implemented: inventory resources and dependencies; export required evidence; validate backup retention decisions; review a destroy plan; obtain explicit approval; execute only the approved scope; inspect for remaining billable resources. Never remove the Terraform backend before confirming managed resources are gone and preserving state/history.
