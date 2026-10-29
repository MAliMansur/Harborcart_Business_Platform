import uuid
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Company(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    approval_threshold_minor = models.PositiveBigIntegerField(default=50000)
    credit_limit_minor = models.PositiveBigIntegerField(default=1000000)
    credit_used_minor = models.PositiveBigIntegerField(default=0)
    discount_bps = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(discount_bps__lte=5000), name="company_discount_bound"),
            models.CheckConstraint(condition=Q(credit_used_minor__lte=F("credit_limit_minor")), name="company_credit_bound"),
        ]
    def __str__(self): return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        BUYER = "buyer", "Buyer"
        APPROVER = "approver", "Purchasing manager"
        WAREHOUSE = "warehouse", "Warehouse operator"
        FINANCE = "finance", "Finance analyst"
        ADMIN = "admin", "Workspace administrator"
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, choices=Role.choices)


class Product(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    sku = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=40)
    description = models.TextField(blank=True, max_length=1000)
    unit_price_minor = models.PositiveBigIntegerField()
    reorder_point = models.PositiveIntegerField(default=10)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "sku"], name="product_company_sku")]
        indexes = [models.Index(fields=["company", "category", "active"])]
    def __str__(self): return self.name


class Warehouse(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    code = models.CharField(max_length=12)
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=60)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="warehouse_company_code")]


class Stock(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="stock")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock")
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "warehouse"], name="stock_product_warehouse"),
            models.CheckConstraint(condition=Q(reserved__lte=F("on_hand")), name="stock_reservation_bound"),
        ]
    @property
    def available(self): return self.on_hand - self.reserved


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="cart_product_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1) & Q(quantity__lte=1000), name="cart_quantity_bound"),
        ]


class Order(models.Model):
    class Status(models.TextChoices):
        APPROVAL = "awaiting_approval", "Awaiting approval"
        QUEUED = "queued", "Queued for invoicing"
        CONFIRMED = "confirmed", "Confirmed"
        PACKED = "packed", "Packed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    status = models.CharField(max_length=24, choices=Status.choices)
    total_minor = models.PositiveBigIntegerField()
    shipping_address = models.CharField(max_length=350)
    idempotency_key = models.CharField(max_length=80)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    reservation_expires_at = models.DateTimeField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="approvals")
    approved_at = models.DateTimeField(null=True)
    cancellation_reason = models.CharField(max_length=200, blank=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["company", "buyer", "idempotency_key"], name="order_idempotency_unique")]
        indexes = [models.Index(fields=["company", "status", "created_at"])]
    @property
    def number(self): return "HC-" + self.id.hex[:10].upper()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    sku = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    unit_price_minor = models.PositiveBigIntegerField()
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="order_product_unique"),
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_quantity_positive"),
        ]
    @property
    def line_total(self): return self.quantity * self.unit_price_minor


class StockMovement(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    kind = models.CharField(max_length=24)
    on_hand_delta = models.IntegerField(default=0)
    reserved_delta = models.IntegerField(default=0)
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)


class Invoice(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="invoice")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    total_minor = models.PositiveBigIntegerField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    issued_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True)
    @property
    def number(self): return "INV-" + self.order_id.hex[:10].upper()


class Payment(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    reference = models.CharField(max_length=80)
    amount_minor = models.PositiveBigIntegerField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "reference"], name="payment_reference_unique")]


class Shipment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="shipment")
    tracking_number = models.CharField(max_length=40, unique=True)
    carrier = models.CharField(max_length=50, default="Sandbox Logistics")
    shipped_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True)


class ReturnCase(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        RECEIVED = "received", "Received"
        REFUNDED = "refunded", "Refund recorded"
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="return_case")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    reason = models.CharField(max_length=300)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    created_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(null=True)


class Refund(models.Model):
    return_case = models.OneToOneField(ReturnCase, on_delete=models.PROTECT)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    amount_minor = models.PositiveBigIntegerField()
    reference = models.CharField(max_length=80)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "reference"], name="refund_reference_unique")]


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        RETRY = "retry", "Retry scheduled"
        DONE = "done", "Completed"
        DEAD = "dead", "Dead letter"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    deduplication_key = models.CharField(max_length=140, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True)
    lease_token = models.UUIDField(null=True)
    last_error = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True)
    class Meta:
        indexes = [models.Index(fields=["status", "available_at"])]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event = models.ForeignKey(OutboxEvent, on_delete=models.PROTECT)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=300)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "event"], name="notification_event_unique")]
        ordering = ["-created_at"]


class AuditEvent(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=30)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "created_at"])]


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=80, unique=True)
    last_seen = models.DateTimeField(default=timezone.now)


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField(default=timezone.now)
