"""Business transactions. Lock order: company, order, stock rows, event.

The company lock deliberately serializes monetary transitions within a tenant.
It makes the first implementation auditable; narrowing it is a later measured
scalability decision. Never perform external network calls inside these blocks.
"""
import hashlib
import json
import re
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import (
    AuditEvent, Cart, CartItem, Company, Invoice, Membership, Order, OrderItem,
    OutboxEvent, Payment, Product, Refund, ReturnCase, Shipment, Stock,
    StockMovement, Warehouse,
)


class BusinessError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def member_for(user):
    if not user.is_authenticated:
        raise BusinessError("authentication_required", "Sign in to continue.", 401)
    try:
        return Membership.objects.select_related("company").get(user=user)
    except Membership.DoesNotExist:
        raise BusinessError("workspace_required", "No workspace is assigned.", 403)


def require(member, *roles):
    if member.role not in roles:
        raise BusinessError("forbidden", "Your role cannot perform this action.", 403)


def audit(company, actor, action, obj, **details):
    return AuditEvent.objects.create(company=company, actor=actor, action=action,
        object_type=obj.__class__.__name__, object_id=str(obj.pk), details=details)


def discounted_price(product, company):
    return (product.unit_price_minor * (10000 - company.discount_bps) + 5000) // 10000


def visible_orders(member):
    qs = Order.objects.filter(company_id=member.company_id)
    if member.role == Membership.Role.BUYER:
        qs = qs.filter(buyer_id=member.user_id)
    return qs


def order_for(member, order_id, lock=False):
    qs = visible_orders(member)
    if lock: qs = qs.select_for_update()
    order = qs.filter(pk=order_id).first()
    if order is None:
        raise BusinessError("not_found", "Order not found.", 404)
    return order


def event(order, kind):
    return OutboxEvent.objects.get_or_create(
        deduplication_key=kind + ":" + str(order.id),
        defaults={"company": order.company, "order": order, "kind": kind},
    )[0]


def ensure_integer(value, name, minimum=1, maximum=1000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise BusinessError("invalid_input", f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def text_value(value, name, minimum=3, maximum=200):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise BusinessError("invalid_input", f"{name} must contain {minimum}–{maximum} characters.")
    return value.strip()


def payment_reference(value):
    value = text_value(value, "reference", 5, 80)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise BusinessError("invalid_reference", "Use letters, numbers, dots, underscores or hyphens.")
    return value


@transaction.atomic
def set_cart_item(user, product_id, quantity):
    member = member_for(user)
    require(member, "buyer", "approver", "admin")
    ensure_integer(quantity, "quantity", 0)
    Company.objects.select_for_update().get(pk=member.company_id)
    product = Product.objects.filter(pk=product_id, company_id=member.company_id, active=True).first()
    if not product:
        raise BusinessError("not_found", "Product not found.", 404)
    cart, _ = Cart.objects.get_or_create(user=user, defaults={"company_id": member.company_id})
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    if quantity:
        CartItem.objects.update_or_create(cart=cart, product=product, defaults={"quantity": quantity})
    else:
        CartItem.objects.filter(cart=cart, product=product).delete()
    cart.version += 1
    cart.save(update_fields=["version"])
    return cart


def cart_data(user):
    member = member_for(user)
    cart = Cart.objects.filter(user=user, company_id=member.company_id).first()
    if not cart: return {"version": 1, "items": [], "total_minor": 0}
    items = []
    for item in cart.items.select_related("product"):
        price = discounted_price(item.product, member.company)
        items.append({"product_id": item.product_id, "sku": item.product.sku,
                      "name": item.product.name, "quantity": item.quantity,
                      "unit_price_minor": price, "total_minor": price * item.quantity})
    return {"version": cart.version, "items": items, "total_minor": sum(i["total_minor"] for i in items)}


@transaction.atomic
def checkout(user, warehouse_id, shipping_address, cart_version, idempotency_key):
    member = member_for(user)
    require(member, "buyer", "approver", "admin")
    ensure_integer(warehouse_id, "warehouse_id", 1, 2**31-1)
    ensure_integer(cart_version, "cart_version", 1, 2**31-1)
    address = text_value(shipping_address, "shipping_address", 10, 350)
    if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", idempotency_key):
        raise BusinessError("idempotency_required", "Send a stable Idempotency-Key of 8–80 safe characters.")
    fingerprint = hashlib.sha256(json.dumps(
        {"warehouse_id": warehouse_id, "shipping_address": address, "cart_version": cart_version},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    company = Company.objects.select_for_update().get(pk=member.company_id)
    previous = Order.objects.filter(company=company, buyer=user, idempotency_key=idempotency_key).first()
    if previous:
        if previous.request_hash != fingerprint:
            raise BusinessError("idempotency_conflict", "This key was already used with a different request.", 409)
        return previous, True

    warehouse = Warehouse.objects.filter(pk=warehouse_id, company=company).first()
    if not warehouse:
        raise BusinessError("not_found", "Warehouse not found.", 404)
    cart = Cart.objects.select_for_update().filter(user=user, company=company).first()
    if not cart or cart.version != cart_version:
        raise BusinessError("stale_cart", "Refresh your cart before checking out.", 409)
    items = list(cart.items.select_related("product").order_by("product_id"))
    if not items:
        raise BusinessError("empty_cart", "Your cart is empty.", 409)
    if len(items) > 50:
        raise BusinessError("too_many_lines", "A purchase supports at most 50 product lines.")
    stocks = {s.product_id: s for s in Stock.objects.select_for_update().filter(
        warehouse=warehouse, product_id__in=[i.product_id for i in items]).order_by("pk")}
    total = 0
    for item in items:
        if item.product.company_id != company.pk or not item.product.active:
            raise BusinessError("product_unavailable", "A product is no longer available.", 409)
        if item.product_id not in stocks or stocks[item.product_id].available < item.quantity:
            raise BusinessError("insufficient_stock", f"Insufficient stock for {item.product.sku} at this warehouse.", 409)
        total += discounted_price(item.product, company) * item.quantity
    if company.credit_used_minor + total > company.credit_limit_minor:
        raise BusinessError("credit_limit", "This order exceeds the workspace's available credit.", 409)

    status = Order.Status.APPROVAL if total > company.approval_threshold_minor else Order.Status.QUEUED
    order = Order.objects.create(company=company, buyer=user, warehouse=warehouse,
        status=status, total_minor=total, shipping_address=address,
        idempotency_key=idempotency_key, request_hash=fingerprint,
        reservation_expires_at=timezone.now() + timedelta(minutes=settings.RESERVATION_MINUTES))
    for item in items:
        stock = stocks[item.product_id]
        stock.reserved += item.quantity
        stock.save(update_fields=["reserved"])
        OrderItem.objects.create(order=order, product=item.product, sku=item.product.sku,
            name=item.product.name, quantity=item.quantity,
            unit_price_minor=discounted_price(item.product, company))
        StockMovement.objects.create(stock=stock, order=order, actor=user, kind="reserve",
            reserved_delta=item.quantity, reason="Purchase submitted")
    company.credit_used_minor += total
    company.save(update_fields=["credit_used_minor"])
    cart.items.all().delete()
    cart.version += 1
    cart.save(update_fields=["version"])
    if status == Order.Status.QUEUED:
        event(order, "order.accepted")
    audit(company, user, "order.submitted", order, total_minor=total, status=status)
    return order, False


@transaction.atomic
def approve_order(user, order_id):
    member = member_for(user)
    require(member, "approver", "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    order = order_for(member, order_id, lock=True)
    if order.buyer_id == user.pk:
        raise BusinessError("self_approval", "A different person must approve this purchase.", 403)
    if order.status != Order.Status.APPROVAL:
        raise BusinessError("invalid_transition", "Only purchases awaiting approval can be approved.", 409)
    if order.reservation_expires_at <= timezone.now():
        raise BusinessError("reservation_expired", "The stock reservation expired; submit a fresh purchase.", 409)
    order.status = Order.Status.QUEUED
    order.approved_by, order.approved_at = user, timezone.now()
    order.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    event(order, "order.accepted")
    audit(company, user, "order.approved", order)
    return order


def _cancel_locked(company, order, actor, reason, action):
    if order.status == Order.Status.CANCELLED: return order
    if order.status not in {Order.Status.APPROVAL, Order.Status.QUEUED, Order.Status.CONFIRMED}:
        raise BusinessError("invalid_transition", "This purchase can no longer be cancelled.", 409)
    invoice = Invoice.objects.select_for_update().filter(order=order).first()
    if invoice and invoice.status == Invoice.Status.PAID:
        raise BusinessError("paid_order", "A paid purchase must follow the return/refund process.", 409)
    items = list(order.items.order_by("product_id"))
    stocks = {s.product_id: s for s in Stock.objects.select_for_update().filter(
        warehouse=order.warehouse, product_id__in=[i.product_id for i in items]).order_by("pk")}
    for item in items:
        stock = stocks[item.product_id]
        stock.reserved -= item.quantity
        stock.save(update_fields=["reserved"])
        StockMovement.objects.create(stock=stock, order=order, actor=actor, kind="release",
            reserved_delta=-item.quantity, reason=reason)
    company.credit_used_minor -= order.total_minor
    company.save(update_fields=["credit_used_minor"])
    if invoice:
        invoice.status = Invoice.Status.VOID
        invoice.save(update_fields=["status"])
    order.status, order.cancellation_reason = Order.Status.CANCELLED, reason
    order.save(update_fields=["status", "cancellation_reason", "updated_at"])
    audit(company, actor, action, order, reason=reason)
    return order


@transaction.atomic
def cancel_order(user, order_id, reason):
    member = member_for(user)
    require(member, "buyer", "approver", "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    order = order_for(member, order_id, lock=True)
    if member.role == "approver" and order.status != Order.Status.APPROVAL and order.buyer_id != user.pk:
        raise BusinessError("forbidden", "Managers may reject pending requests or cancel their own purchases.", 403)
    return _cancel_locked(company, order, user, text_value(reason, "reason"), "order.cancelled")


@transaction.atomic
def expire_order(order_id):
    snapshot = Order.objects.filter(pk=order_id).values("company_id").first()
    if not snapshot: return False
    company = Company.objects.select_for_update().get(pk=snapshot["company_id"])
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status in {Order.Status.APPROVAL, Order.Status.QUEUED} and order.reservation_expires_at <= timezone.now():
        _cancel_locked(company, order, None, "Reservation deadline exceeded", "order.expired")
        return True
    return False


@transaction.atomic
def fulfill_order(user, order_id, action):
    member = member_for(user)
    require(member, "warehouse", "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    order = order_for(member, order_id, lock=True)
    transitions = {"pack": (Order.Status.CONFIRMED, Order.Status.PACKED),
                   "ship": (Order.Status.PACKED, Order.Status.SHIPPED),
                   "deliver": (Order.Status.SHIPPED, Order.Status.DELIVERED)}
    if action not in transitions:
        raise BusinessError("invalid_action", "Unknown fulfillment action.")
    before, after = transitions[action]
    if order.status == after: return order
    if order.status != before:
        raise BusinessError("invalid_transition", f"This action requires status {before}.", 409)
    if action == "ship":
        items = list(order.items.order_by("product_id"))
        stocks = {s.product_id: s for s in Stock.objects.select_for_update().filter(
            warehouse=order.warehouse, product_id__in=[i.product_id for i in items]).order_by("pk")}
        for item in items:
            stock = stocks[item.product_id]
            stock.reserved -= item.quantity
            stock.on_hand -= item.quantity
            stock.save(update_fields=["reserved", "on_hand"])
            StockMovement.objects.create(stock=stock, order=order, actor=user, kind="ship",
                on_hand_delta=-item.quantity, reserved_delta=-item.quantity, reason="Shipment dispatched")
        Shipment.objects.create(order=order, tracking_number="HC" + order.id.hex.upper())
        event(order, "shipment.dispatched")
    if action == "deliver":
        Shipment.objects.filter(order=order).update(delivered_at=timezone.now())
        event(order, "shipment.delivered")
    order.status = after
    order.save(update_fields=["status", "updated_at"])
    audit(company, user, "order." + action, order)
    return order


@transaction.atomic
def adjust_stock(user, stock_id, delta, reason):
    member = member_for(user)
    require(member, "warehouse", "admin")
    ensure_integer(delta, "delta", -100000, 100000)
    company = Company.objects.select_for_update().get(pk=member.company_id)
    stock = Stock.objects.select_for_update().filter(pk=stock_id, product__company=company,
                                                      warehouse__company=company).first()
    if not stock: raise BusinessError("not_found", "Stock record not found.", 404)
    if stock.on_hand + delta < stock.reserved:
        raise BusinessError("reserved_stock", "Adjustment would remove stock already reserved for purchases.", 409)
    stock.on_hand += delta
    stock.save(update_fields=["on_hand"])
    StockMovement.objects.create(stock=stock, actor=user, kind="adjust", on_hand_delta=delta,
                                 reason=text_value(reason, "reason"))
    audit(company, user, "inventory.adjusted", stock, delta=delta)
    return stock


@transaction.atomic
def record_payment(user, invoice_id, reference):
    member = member_for(user)
    require(member, "finance", "admin")
    reference = payment_reference(reference)
    company = Company.objects.select_for_update().get(pk=member.company_id)
    invoice = Invoice.objects.select_for_update().filter(pk=invoice_id, company=company).first()
    if not invoice: raise BusinessError("not_found", "Invoice not found.", 404)
    if invoice.status == Invoice.Status.PAID:
        existing = Payment.objects.get(invoice=invoice)
        if existing.reference != reference:
            raise BusinessError("payment_conflict", "This invoice has already been paid with another reference.", 409)
        return invoice
    if invoice.status != Invoice.Status.OPEN:
        raise BusinessError("invalid_transition", "Only open invoices can be settled.", 409)
    if Payment.objects.filter(company=company, reference=reference).exists():
        raise BusinessError("payment_conflict", "Payment reference already used.", 409)
    Payment.objects.create(invoice=invoice, company=company, reference=reference,
                           amount_minor=invoice.total_minor, recorded_by=user)
    invoice.status, invoice.paid_at = Invoice.Status.PAID, timezone.now()
    invoice.save(update_fields=["status", "paid_at"])
    company.credit_used_minor -= invoice.total_minor
    company.save(update_fields=["credit_used_minor"])
    audit(company, user, "invoice.payment_recorded", invoice, amount_minor=invoice.total_minor)
    event(invoice.order, "invoice.paid")
    return invoice


@transaction.atomic
def request_return(user, order_id, reason):
    member = member_for(user)
    require(member, "buyer", "approver", "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    order = order_for(member, order_id, lock=True)
    if order.buyer_id != user.pk and member.role != "admin":
        raise BusinessError("forbidden", "Only the buyer can request this return.", 403)
    existing = ReturnCase.objects.filter(order=order).first()
    if existing: return existing
    if order.status != Order.Status.DELIVERED or not Invoice.objects.filter(order=order, status="paid").exists():
        raise BusinessError("invalid_transition", "Full returns require a delivered purchase and a paid invoice.", 409)
    case = ReturnCase.objects.create(order=order, company=company, reason=text_value(reason, "reason", 5, 300))
    audit(company, user, "return.requested", case)
    return case


@transaction.atomic
def receive_return(user, case_id):
    member = member_for(user)
    require(member, "warehouse", "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    case = ReturnCase.objects.select_for_update().filter(pk=case_id, company=company).first()
    if not case: raise BusinessError("not_found", "Return not found.", 404)
    if case.status == ReturnCase.Status.RECEIVED: return case
    if case.status != ReturnCase.Status.REQUESTED:
        raise BusinessError("invalid_transition", "This return cannot be received.", 409)
    order = Order.objects.select_for_update().get(pk=case.order_id)
    items = list(order.items.order_by("product_id"))
    stocks = {s.product_id: s for s in Stock.objects.select_for_update().filter(
        warehouse=order.warehouse, product_id__in=[i.product_id for i in items]).order_by("pk")}
    for item in items:
        stock = stocks[item.product_id]
        stock.on_hand += item.quantity
        stock.save(update_fields=["on_hand"])
        StockMovement.objects.create(stock=stock, order=order, actor=user, kind="return",
                                     on_hand_delta=item.quantity, reason="Returned items received")
    case.status, case.received_at = ReturnCase.Status.RECEIVED, timezone.now()
    case.save(update_fields=["status", "received_at"])
    audit(company, user, "return.received", case)
    return case


@transaction.atomic
def record_refund(user, case_id, reference):
    member = member_for(user)
    require(member, "finance", "admin")
    reference = payment_reference(reference)
    company = Company.objects.select_for_update().get(pk=member.company_id)
    case = ReturnCase.objects.select_for_update().filter(pk=case_id, company=company).first()
    if not case: raise BusinessError("not_found", "Return not found.", 404)
    existing = Refund.objects.filter(return_case=case).first()
    if existing:
        if existing.reference != reference:
            raise BusinessError("refund_conflict", "This return has already been refunded.", 409)
        return existing
    if case.status != ReturnCase.Status.RECEIVED:
        raise BusinessError("invalid_transition", "Warehouse must receive the goods before a refund is recorded.", 409)
    if Refund.objects.filter(company=company, reference=reference).exists():
        raise BusinessError("refund_conflict", "Refund reference already used.", 409)
    order = Order.objects.select_for_update().get(pk=case.order_id)
    invoice = Invoice.objects.get(order=order, status=Invoice.Status.PAID)
    refund = Refund.objects.create(return_case=case, company=company, reference=reference,
                                    amount_minor=invoice.total_minor, recorded_by=user)
    case.status = ReturnCase.Status.REFUNDED
    case.save(update_fields=["status"])
    order.status = Order.Status.REFUNDED
    order.save(update_fields=["status", "updated_at"])
    event(order, "return.refunded")
    audit(company, user, "return.refund_recorded", case, amount_minor=refund.amount_minor)
    return refund


@transaction.atomic
def retry_event(user, event_id):
    member = member_for(user)
    require(member, "admin")
    company = Company.objects.select_for_update().get(pk=member.company_id)
    job = OutboxEvent.objects.select_for_update().filter(pk=event_id, company=company).first()
    if not job: raise BusinessError("not_found", "Job not found.", 404)
    if job.status not in {OutboxEvent.Status.DEAD, OutboxEvent.Status.RETRY}:
        raise BusinessError("invalid_transition", "Only failed or retrying jobs can be replayed.", 409)
    audit(company, user, "outbox.replayed", job, previous_attempts=job.attempts, previous_error=job.last_error)
    job.status, job.attempts, job.available_at = OutboxEvent.Status.PENDING, 0, timezone.now()
    job.lease_token, job.lease_until = None, None
    job.save(update_fields=["status", "attempts", "available_at", "lease_token", "lease_until"])
    return job
