import hmac
from django.conf import settings
from django.db import DatabaseError
from django.db.models import F, Min
from django.http import HttpResponse
from django.utils import timezone
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST
from .models import Order, OutboxEvent, Stock, WorkerHeartbeat

def metrics(request):
    expected = "Bearer " + settings.METRICS_TOKEN
    if not settings.METRICS_TOKEN or not hmac.compare_digest(request.headers.get("Authorization",""), expected):
        return HttpResponse("Unauthorized\n",status=401)
    registry = CollectorRegistry()
    now = timezone.now()
    try:
        orders = Gauge("harborcart_orders","Current orders by business state",["status"],registry=registry)
        for status in Order.Status.values: orders.labels(status).set(Order.objects.filter(status=status).count())
        jobs = Gauge("harborcart_jobs","Durable outbox jobs by state",["status"],registry=registry)
        for status in OutboxEvent.Status.values: jobs.labels(status).set(OutboxEvent.objects.filter(status=status).count())
        oldest = OutboxEvent.objects.filter(status__in=["pending","retry","processing"]).aggregate(v=Min("created_at"))["v"]
        Gauge("harborcart_queue_oldest_seconds","Age of oldest unfinished job",registry=registry).set(
            max(0,(now-oldest).total_seconds()) if oldest else 0)
        hb = WorkerHeartbeat.objects.order_by("-last_seen").first()
        Gauge("harborcart_worker_heartbeat_age_seconds","Age of newest worker heartbeat; 1e9 if absent",registry=registry).set(
            max(0,(now-hb.last_seen).total_seconds()) if hb else 1e9)
        Gauge("harborcart_low_stock_records","Warehouse SKU records at reorder point",registry=registry).set(
            Stock.objects.filter(on_hand__lte=F("reserved")+F("product__reorder_point")).count())
    except DatabaseError:
        return HttpResponse("Database unavailable\n",status=503)
    return HttpResponse(generate_latest(registry),content_type=CONTENT_TYPE_LATEST)
