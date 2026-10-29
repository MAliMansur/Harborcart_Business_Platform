import functools
import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import F, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from . import services
from .models import (
    AuditEvent, Company, Invoice, LoginAttempt, Membership, Notification,
    Order, OutboxEvent, Product, Refund, ReturnCase, Stock, Warehouse, WorkerHeartbeat,
)


class WorkspaceLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    def post(self, request, *args, **kwargs):
        raw = request.POST.get("username", "").casefold()[:150] + "|" + request.META.get("REMOTE_ADDR", "")[:64]
        self.attempt_key = hmac.new(settings.SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
        with transaction.atomic():
            attempt, _ = LoginAttempt.objects.get_or_create(key=self.attempt_key)
            attempt = LoginAttempt.objects.select_for_update().get(pk=attempt.pk)
            if attempt.window_start < timezone.now() - timedelta(minutes=10):
                attempt.attempts, attempt.window_start = 0, timezone.now()
            if attempt.attempts >= 10:
                return render(request, self.template_name, {"form": self.get_form(),
                    "throttled": True}, status=429)
            attempt.attempts += 1
            attempt.save(update_fields=["attempts", "window_start"])
        return super().post(request, *args, **kwargs)
    def form_valid(self, form):
        LoginAttempt.objects.filter(key=self.attempt_key).delete()
        return super().form_valid(form)


def api(methods):
    def decorate(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error":"method_not_allowed","message":"Method not allowed."}, status=405)
            try:
                request.member = services.member_for(request.user)
                return view(request, *args, **kwargs)
            except services.BusinessError as error:
                return JsonResponse({"error":error.code,"message":error.message}, status=error.status)
            except (ValueError, TypeError, ValidationError):
                return JsonResponse({"error":"invalid_input","message":"Invalid request values."}, status=400)
        return wrapped
    return decorate


def body(request, allowed):
    if request.content_type != "application/json":
        raise services.BusinessError("content_type", "Send application/json.", 415)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeError):
        raise services.BusinessError("invalid_json", "Invalid JSON.")
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise services.BusinessError("invalid_fields", "Unexpected request fields.")
    return data


def order_json(order):
    return {"id":str(order.id), "number":order.number, "status":order.status,
            "status_label":order.get_status_display(), "total_minor":order.total_minor,
            "created_at":order.created_at.isoformat(), "warehouse_id":order.warehouse_id,
            "url":"/orders/" + str(order.id) + "/"}


@login_required
def dashboard(request):
    member = services.member_for(request.user)
    orders = services.visible_orders(member)
    company = member.company
    paid = Invoice.objects.filter(order__in=orders, status="paid").aggregate(n=Sum("total_minor"))["n"] or 0
    refunded = Refund.objects.filter(return_case__order__in=orders).aggregate(n=Sum("amount_minor"))["n"] or 0
    status_rows = [{"label":label,"count":orders.filter(status=value).count(),"status":value}
                   for value,label in Order.Status.choices]
    low = Stock.objects.filter(product__company=company, warehouse__company=company,
        on_hand__lte=F("reserved") + F("product__reorder_point")).select_related("product","warehouse")[:6]
    return render(request, "commerce/dashboard.html", {
        "page":"dashboard","title":"Workspace overview","orders_total":orders.count(),
        "approval_count":orders.filter(status="awaiting_approval").count(),
        "in_flight":orders.filter(status__in=["queued","confirmed","packed","shipped"]).count(),
        "net_paid":paid-refunded,"credit_remaining":company.credit_limit_minor-company.credit_used_minor,
        "status_rows":status_rows,"recent_orders":orders.select_related("buyer","warehouse")[:7],
        "low_stock":low,"recent_audit":AuditEvent.objects.filter(company=company).select_related("actor")[:6],
    })


@login_required
def catalog(request):
    member = services.member_for(request.user)
    products = Product.objects.filter(company=member.company, active=True).prefetch_related("stock")
    q, category = request.GET.get("q", "")[:64], request.GET.get("category", "")[:40]
    if q: products = products.filter(name__icontains=q)
    if category: products = products.filter(category=category)
    cards = []
    for product in products.order_by("category", "name")[:60]:
        product.customer_price = services.discounted_price(product, member.company)
        product.available_count = sum(s.available for s in product.stock.all())
        cards.append(product)
    return render(request, "commerce/catalog.html", {"page":"catalog","title":"Product catalog",
        "products":cards,"categories":Product.objects.filter(company=member.company, active=True).values_list("category",flat=True).distinct(),
        "warehouses":Warehouse.objects.filter(company=member.company),"q":q,"category":category,
        "checkout_key":uuid.uuid4().hex})


@login_required
def orders_page(request, queue=None):
    member = services.member_for(request.user)
    if queue == "approvals": services.require(member, "approver", "admin")
    if queue == "fulfillment": services.require(member, "warehouse", "admin")
    orders = services.visible_orders(member).select_related("buyer","warehouse")
    if queue == "approvals": orders = orders.filter(status="awaiting_approval")
    elif queue == "fulfillment": orders = orders.filter(status__in=["confirmed","packed","shipped"])
    else:
        status = request.GET.get("status", "")
        if status in Order.Status.values: orders = orders.filter(status=status)
    return render(request, "commerce/orders.html", {"page":queue or "orders",
        "title":{"approvals":"Purchasing approvals","fulfillment":"Fulfillment desk"}.get(queue,"Orders"),
        "orders":orders[:100],"status_choices":Order.Status.choices,"queue":queue,
        "selected_status":request.GET.get("status","")})


@login_required
def order_detail(request, order_id):
    member = services.member_for(request.user)
    order = services.order_for(member, order_id)
    return render(request, "commerce/order_detail.html", {"page":"orders","title":order.number,
        "order":order,"items":order.items.all(),"invoice":Invoice.objects.filter(order=order).first(),
        "case":ReturnCase.objects.filter(order=order).first(),
        "events":OutboxEvent.objects.filter(order=order).order_by("created_at"),
        "timeline":AuditEvent.objects.filter(company_id=member.company_id, object_id=str(order.id)).select_related("actor")})


@login_required
def inventory(request):
    member = services.member_for(request.user)
    services.require(member,"warehouse","admin")
    stocks = Stock.objects.filter(product__company_id=member.company_id,
        warehouse__company_id=member.company_id).select_related("product","warehouse").order_by("warehouse__code","product__sku")
    return render(request,"commerce/inventory.html",{"page":"inventory","title":"Inventory control","stocks":stocks})


@login_required
def finance(request):
    member = services.member_for(request.user)
    services.require(member,"finance","admin")
    invoices = Invoice.objects.filter(company_id=member.company_id).select_related("order","order__buyer").order_by("-issued_at")
    return render(request,"commerce/finance.html",{"page":"finance","title":"Finance desk","invoices":invoices[:100],
        "open_balance":invoices.filter(status="open").aggregate(n=Sum("total_minor"))["n"] or 0,
        "paid_total":invoices.filter(status="paid").aggregate(n=Sum("total_minor"))["n"] or 0,
        "refunds":Refund.objects.filter(company_id=member.company_id).select_related("return_case__order").order_by("-created_at")[:30]})


@login_required
def returns_page(request):
    member = services.member_for(request.user)
    returns = ReturnCase.objects.filter(order__in=services.visible_orders(member)).select_related("order","order__buyer").order_by("-created_at")
    return render(request,"commerce/returns.html",{"page":"returns","title":"Returns and refunds","returns":returns[:100]})


@login_required
def operations(request):
    member = services.member_for(request.user)
    services.require(member,"admin")
    jobs = OutboxEvent.objects.filter(company_id=member.company_id)
    heartbeats = WorkerHeartbeat.objects.order_by("-last_seen")
    return render(request,"commerce/operations.html",{"page":"operations","title":"Operations center",
        "jobs":jobs.select_related("order").order_by("-created_at")[:60],
        "pending":jobs.filter(status__in=["pending","retry","processing"]).count(),
        "dead":jobs.filter(status="dead").count(),"done":jobs.filter(status="done").count(),
        "heartbeats":heartbeats,"now":timezone.now()})


@login_required
def audit_page(request):
    member = services.member_for(request.user)
    services.require(member,"admin","finance","approver")
    rows = AuditEvent.objects.filter(company_id=member.company_id).select_related("actor")
    return render(request,"commerce/audit.html",{"page":"audit","title":"Audit trail","rows":rows[:150]})


@login_required
def notifications(request):
    return render(request,"commerce/notifications.html",{"page":"notifications","title":"Your notifications",
        "notifications":Notification.objects.filter(user=request.user)[:100]})


@api(["GET","POST"])
def cart_api(request):
    if request.method == "POST":
        data=body(request,["product_id","quantity"])
        services.set_cart_item(request.user,data.get("product_id"),data.get("quantity"))
    return JsonResponse(services.cart_data(request.user))


@api(["POST"])
def checkout_api(request):
    data=body(request,["warehouse_id","shipping_address","cart_version"])
    order,replayed=services.checkout(request.user,data.get("warehouse_id"),data.get("shipping_address"),
        data.get("cart_version"),request.headers.get("Idempotency-Key"))
    return JsonResponse({**order_json(order),"replayed":replayed},status=200 if replayed else 201)


@api(["GET"])
def order_api(request, order_id):
    return JsonResponse(order_json(services.order_for(request.member,order_id)))


@api(["POST"])
def order_action_api(request, order_id):
    data=body(request,["action","reason"])
    action=data.get("action")
    if action=="approve": order=services.approve_order(request.user,order_id)
    elif action=="cancel": order=services.cancel_order(request.user,order_id,data.get("reason"))
    elif action in {"pack","ship","deliver"}: order=services.fulfill_order(request.user,order_id,action)
    elif action=="return":
        case=services.request_return(request.user,order_id,data.get("reason"))
        return JsonResponse({"id":case.pk,"status":case.status,"url":"/returns/"},status=201)
    else: raise services.BusinessError("invalid_action","Unknown action.")
    return JsonResponse(order_json(order))


@api(["POST"])
def stock_api(request, stock_id):
    data=body(request,["delta","reason"])
    stock=services.adjust_stock(request.user,stock_id,data.get("delta"),data.get("reason"))
    return JsonResponse({"id":stock.pk,"on_hand":stock.on_hand,"reserved":stock.reserved,"available":stock.available})


@api(["POST"])
def payment_api(request, invoice_id):
    data=body(request,["reference"])
    invoice=services.record_payment(request.user,invoice_id,data.get("reference"))
    return JsonResponse({"id":invoice.pk,"status":invoice.status})


@api(["POST"])
def return_api(request, case_id):
    data=body(request,["action","reference"])
    if data.get("action")=="receive":
        case=services.receive_return(request.user,case_id)
        return JsonResponse({"id":case.pk,"status":case.status})
    if data.get("action")=="refund":
        refund=services.record_refund(request.user,case_id,data.get("reference"))
        return JsonResponse({"id":refund.pk,"amount_minor":refund.amount_minor})
    raise services.BusinessError("invalid_action","Unknown return action.")


@api(["POST"])
def replay_api(request, event_id):
    body(request,[])
    job=services.retry_event(request.user,event_id)
    return JsonResponse({"id":str(job.id),"status":job.status})


@api(["POST"])
def notification_api(request, notification_id):
    body(request,[])
    changed=Notification.objects.filter(pk=notification_id,user=request.user).update(read_at=timezone.now())
    if not changed: raise services.BusinessError("not_found","Notification not found.",404)
    return JsonResponse({"read":True})


def health(request):
    return JsonResponse({"status":"alive","service":"harborcart-business","version":"0.2.0"})


def readiness(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        # A bare database connection is insufficient if migrations are missing.
        Company.objects.exists()
    except DatabaseError:
        return JsonResponse({"status":"unready"},status=503)
    return JsonResponse({"status":"ready"})


def error403(request, exception=None):
    return render(request,"commerce/error.html",{"title":"Access restricted","message":"Your role cannot access this workspace action."},status=403)


def error404(request, exception=None):
    return render(request,"commerce/error.html",{"title":"Not found","message":"This resource is unavailable in your workspace."},status=404)
