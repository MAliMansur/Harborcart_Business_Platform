# Runbook: missing or stale observability
Business risk: the system may be unhealthy while dashboards look empty or frozen.

Inspect local Prometheus /targets and /alerts, then:
```bash
docker compose ps prometheus grafana web worker
docker compose logs --tail=100 prometheus grafana
docker compose exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose exec -T prometheus promtool check rules /etc/prometheus/alerts.yml
```
Check scrape HTTP status, target address, credentials-file mount and permissions, DNS/network reachability and clock/time range. A healthy Grafana login does not prove metrics collection.

Compare up{job="harborcart"}, harborcart_queue_oldest_seconds and harborcart_worker_heartbeat_age_seconds. Review absent-series behavior separately from a zero value. These metrics do not measure checkout latency or success rate.

Keep secrets out of command output. Restore valid authentication and config; do not make /metrics public. Validate fresh samples and an intentionally triggered local alert. Configure a separate alert receiver and a dead-man/heartbeat path before production; this local profile only displays alerts in Prometheus.
