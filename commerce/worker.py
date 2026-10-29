"""Durable outbox processing with expiring ownership tokens and bounded retries."""
import json
import logging
import uuid
from datetime import timedelta
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from .models import Company, Invoice, Notification, Order, OutboxEvent, WorkerHeartbeat
from .services import audit, expire_order
LOG = logging.getLogger("harborcart")


@transaction.atomic
def claim_event():
    now = timezone.now()
    eligible = (Q(status__in=["pending", "retry"], available_at__lte=now) |
                Q(status="processing", lease_until__lte=now))
    qs = OutboxEvent.objects.filter(eligible).order_by("created_at", "id")
    if connection.features.has_select_for_update_skip_locked:
        qs = qs.select_for_update(skip_locked=True)
    else:
        qs = qs.select_for_update()
    job = qs.first()
    if not job: return None
    if job.attempts >= settings.MAX_JOB_ATTEMPTS:
        job.status, job.last_error = "dead", "LeaseRecoveryLimit"
        job.save(update_fields=["status", "last_error"])
        return job.id, None
    job.status = "processing"
    job.attempts += 1
    job.lease_token = uuid.uuid4()
    job.lease_until = now + timedelta(seconds=settings.WORKER_LEASE_SECONDS)
    job.save(update_fields=["status", "attempts", "lease_token", "lease_until"])
    return job.id, job.lease_token


def process_event(event_id, token):
    snapshot = OutboxEvent.objects.filter(pk=event_id).values("company_id", "order_id").first()
    if not snapshot or token is None: return False
    with transaction.atomic():
        company = Company.objects.select_for_update().get(pk=snapshot["company_id"])
        order = Order.objects.select_for_update().get(pk=snapshot["order_id"])
        job = OutboxEvent.objects.select_for_update().get(pk=event_id)
        if job.status != "processing" or job.lease_token != token or job.lease_until <= timezone.now():
            return False
        if settings.WORKER_FAIL_KIND == job.kind:
            raise RuntimeError("InjectedWorkerFailure")
        if job.kind == "order.accepted":
            if order.status == Order.Status.QUEUED:
                if order.reservation_expires_at <= timezone.now():
                    # Release the same company/order through a nested atomic block.
                    expire_order(order.id)
                else:
                    Invoice.objects.get_or_create(order=order, defaults={
                        "company": company, "total_minor": order.total_minor,
                        "due_at": timezone.now() + timedelta(days=14)})
                    order.status = Order.Status.CONFIRMED
                    order.save(update_fields=["status", "updated_at"])
                    audit(company, None, "invoice.generated", order)
                    Notification.objects.get_or_create(user=order.buyer, event=job,
                        defaults={"title": "Your purchase is confirmed",
                                  "body": order.number + " is ready for warehouse processing."})
        elif job.kind in {"shipment.dispatched", "shipment.delivered", "invoice.paid", "return.refunded"}:
            titles = {"shipment.dispatched": "Your order has shipped",
                      "shipment.delivered": "Delivery confirmed",
                      "invoice.paid": "Payment recorded",
                      "return.refunded": "Refund recorded"}
            Notification.objects.get_or_create(user=order.buyer, event=job,
                defaults={"title": titles[job.kind], "body": order.number + " · " + order.get_status_display()})
        else:
            raise ValueError("UnknownEventKind")
        job.status, job.completed_at = "done", timezone.now()
        job.lease_token, job.lease_until, job.last_error = None, None, ""
        job.save(update_fields=["status", "completed_at", "lease_token", "lease_until", "last_error"])
    return True


@transaction.atomic
def fail_event(event_id, token, error):
    job = OutboxEvent.objects.select_for_update().get(pk=event_id)
    if job.status != "processing" or job.lease_token != token: return
    job.status = "dead" if job.attempts >= settings.MAX_JOB_ATTEMPTS else "retry"
    job.last_error = type(error).__name__[:80]  # Never persist arbitrary exception data.
    job.available_at = timezone.now() + timedelta(seconds=min(60, 2 ** job.attempts))
    job.lease_token, job.lease_until = None, None
    job.save(update_fields=["status", "last_error", "available_at", "lease_token", "lease_until"])
    LOG.warning(json.dumps({"event":"job_failed","job_id":str(job.id),
                            "attempt":job.attempts,"status":job.status,"error":job.last_error}))


def process_one():
    claim = claim_event()
    if not claim: return False
    event_id, token = claim
    try:
        process_event(event_id, token)
    except Exception as error:
        fail_event(event_id, token, error)
    return True


def expire_due():
    due = list(Order.objects.filter(status__in=["awaiting_approval", "queued"],
            reservation_expires_at__lte=timezone.now()).values_list("id", flat=True)[:100])
    return sum(expire_order(pk) for pk in due)


def heartbeat(name):
    WorkerHeartbeat.objects.update_or_create(name=name, defaults={"last_seen": timezone.now()})
