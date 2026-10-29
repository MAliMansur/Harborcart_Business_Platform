# Versions, provenance and official references
Reviewed 2026-10-26. A supported branch is distinct from a fully patched runtime, and an official release is distinct from a successfully pulled container image.

| Component | Selected / observed | Evidence and limitation |
|---|---|---|
| Python | Accepted 3.12–3.14; executed 3.12.14; container target 3.12.16 | Python 3.12.16 security release announced Oct 25. Local runtime patch differs; public release blocked pending patch verification. |
| Django | 5.2.18 LTS | Official download lists 5.2 LTS extended support through April 2028. Installed and tested. |
| Psycopg | 3.3.6 with binary wheel | Installed. PostgreSQL connection/concurrency not exercised here. |
| Gunicorn | 26.2.0 | Installed and used by real HTTP smoke. Official news lists newer 26.2.2; the package index used here did not provide it. Review and upgrade this pin before public release. |
| WhiteNoise | 6.12.0 | Installed; collectstatic and actual HTTP CSS retrieval verified. |
| prometheus-client | 0.26.0 | Installed; authenticated metrics endpoint tested. |
| PostgreSQL | Image target 18.6-bookworm | Official PostgreSQL 18.6 release Aug 13. Image pull/runtime not verified. |
| Prometheus | Image target v3.13.5 | 3.13 LTS supported to July 31, 2027. Pull, promtool and scrape runtime pending. |
| Grafana | Image target 13.2.4 | Official OSS download Oct 13. Pull and dashboard rendering pending. |
| Bandit / pip-audit | 1.9.4 / 2.10.1 | Installed; results in evidence/. |
| GitHub actions | checkout v7.0.0; setup-python v6.3.0 commit pins | Workflows supplied; not run on GitHub. |

Dependency artifacts are hash-locked in requirements.lock and requirements-security.lock. A digest is not supplied for a container that was never pulled; resolve and record digests during the container gate.

Primary references:
- Python security release: https://www.python.org/downloads/latest/python3.12/
- Django releases/support: https://www.djangoproject.com/download/
- Django deployment checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Django transactions: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- PostgreSQL row locks in Django: https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update
- Psycopg release history: https://www.psycopg.org/psycopg3/docs/news.html
- Gunicorn release news: https://gunicorn.org/2026-news/
- WhiteNoise Django integration: https://whitenoise.readthedocs.io/en/stable/django.html
- PostgreSQL 18.6: https://www.postgresql.org/docs/release/18.6/
- Docker PostgreSQL 18 volume location: https://docs.docker.com/guides/postgresql/
- Docker Compose startup order: https://docs.docker.com/compose/how-tos/startup-order/
- Prometheus LTS policy: https://prometheus.io/docs/introduction/release-cycle/
- Prometheus releases: https://github.com/prometheus/prometheus/releases
- Prometheus scrape configuration: https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- Grafana OSS Docker download: https://grafana.com/grafana/download?edition=oss&platform=docker
- GitHub environment protection: https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments

Recheck AWS service versions, regional availability, EKS support windows and prices immediately before designing or applying paid infrastructure. No remembered cloud price or unsupported tag should become a deployment assumption.
