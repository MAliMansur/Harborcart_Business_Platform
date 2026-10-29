import json
import uuid
from io import StringIO
from django.core.management import call_command
from django.core.management.base import CommandError
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from commerce import services as s, worker
from commerce.models import *

class BusinessFixture:
    @classmethod
    def setUpTestData(cls):
        cls.company=Company.objects.create(name="Atlas",slug="atlas",approval_threshold_minor=50000,credit_limit_minor=1000000)
        cls.foreign=Company.objects.create(name="Boreal",slug="boreal")
        cls.users={}
        for name,role in [("buyer","buyer"),("buyer2","buyer"),("manager","approver"),("warehouse","warehouse"),
                          ("finance","finance"),("operator","admin")]:
            user=get_user_model().objects.create_user(username=name,password="Test-password-only-12345")
            Membership.objects.create(user=user,company=cls.company,role=role)
            cls.users[name]=user
        cls.rival=get_user_model().objects.create_user(username="rival",password="Test-password-only-12345")
        Membership.objects.create(user=cls.rival,company=cls.foreign,role="admin")
        cls.warehouse=Warehouse.objects.create(company=cls.company,code="EAST",name="East",city="Newark")
        cls.foreign_warehouse=Warehouse.objects.create(company=cls.foreign,code="NORTH",name="North",city="Portland")
        cls.product=Product.objects.create(company=cls.company,sku="NET-1",name="Network switch",category="Network",unit_price_minor=12000)
        cls.foreign_product=Product.objects.create(company=cls.foreign,sku="SECRET",name="Foreign router",category="Network",unit_price_minor=9999)
        cls.stock=Stock.objects.create(product=cls.product,warehouse=cls.warehouse,on_hand=20)
        Stock.objects.create(product=cls.foreign_product,warehouse=cls.foreign_warehouse,on_hand=10)
    def purchase(self,quantity=1,who="buyer",key=None):
        user=self.users[who]
        s.set_cart_item(user,self.product.pk,quantity)
        version=s.cart_data(user)["version"]
        return s.checkout(user,self.warehouse.pk,"100 Market Street, Receiving Bay A",version,key or uuid.uuid4().hex)[0]
    def confirmed(self,quantity=1):
        order=self.purchase(quantity)
        if order.status=="awaiting_approval": s.approve_order(self.users["manager"],order.pk)
        while worker.process_one(): pass
        order.refresh_from_db()
        return order
    def delivered(self):
        order=self.confirmed()
        for action in ("pack","ship","deliver"): s.fulfill_order(self.users["warehouse"],order.pk,action)
        order.refresh_from_db()
        return order
    def paid_delivered(self):
        order=self.delivered()
        s.record_payment(self.users["finance"],order.invoice.pk,"BANK-REFERENCE-001")
        return order
    def assertError(self,code,fn,*args,**kwargs):
        with self.assertRaises(s.BusinessError) as ctx: fn(*args,**kwargs)
        self.assertEqual(ctx.exception.code,code)

class TransactionRules(BusinessFixture,TestCase):
    def test_checkout_reserves_credit_stock_and_outbox(self):
        order=self.purchase(2);self.stock.refresh_from_db();self.company.refresh_from_db()
        self.assertEqual((order.total_minor,self.stock.reserved,self.company.credit_used_minor),(24000,2,24000))
        self.assertEqual(OutboxEvent.objects.filter(order=order).count(),1)
        self.assertEqual(s.cart_data(self.users["buyer"])["items"],[])
    def test_no_partial_checkout_when_stock_insufficient(self):
        self.assertError("insufficient_stock",self.purchase,21)
        self.stock.refresh_from_db();self.company.refresh_from_db()
        self.assertEqual((Order.objects.count(),OutboxEvent.objects.count(),self.stock.reserved,self.company.credit_used_minor),(0,0,0,0))
        self.assertEqual(len(s.cart_data(self.users["buyer"])["items"]),1)
    def test_credit_limit_rejects_without_reserving_stock(self):
        Company.objects.filter(pk=self.company.pk).update(credit_limit_minor=1000)
        self.assertError("credit_limit",self.purchase)
        self.stock.refresh_from_db();self.assertEqual(self.stock.reserved,0)
    def test_repeated_checkout_returns_same_order(self):
        user=self.users["buyer"];s.set_cart_item(user,self.product.pk,2);version=s.cart_data(user)["version"]
        args=(user,self.warehouse.pk,"100 Market Street, Receiving Bay A",version,"checkout-key-001")
        first,_=s.checkout(*args);second,replayed=s.checkout(*args)
        self.assertTrue(replayed);self.assertEqual(first.pk,second.pk)
        self.stock.refresh_from_db();self.assertEqual(self.stock.reserved,2);self.assertEqual(Order.objects.count(),1)
    def test_reused_key_with_different_payload_conflicts(self):
        order=self.purchase(key="checkout-key-001")
        self.assertError("idempotency_conflict",s.checkout,self.users["buyer"],self.warehouse.pk,
            "A different address in Newark",2,"checkout-key-001")
        self.assertEqual(Order.objects.count(),1)
    def test_stale_cart_conflicts(self):
        s.set_cart_item(self.users["buyer"],self.product.pk,1)
        self.assertError("stale_cart",s.checkout,self.users["buyer"],self.warehouse.pk,
            "100 Market Street, Receiving Bay A",1,"stale-cart-key")
    def test_empty_cart_rejected(self):
        s.set_cart_item(self.users["buyer"],self.product.pk,0)
        self.assertError("empty_cart",s.checkout,self.users["buyer"],self.warehouse.pk,
            "100 Market Street, Receiving Bay A",s.cart_data(self.users["buyer"])["version"],"empty-cart-key")
    def test_price_snapshot_survives_catalog_price_change(self):
        order=self.purchase()
        Product.objects.filter(pk=self.product.pk).update(unit_price_minor=999999)
        self.assertEqual(order.items.get().unit_price_minor,12000)
        self.assertEqual(order.total_minor,12000)
    def test_contract_discount_is_integer_and_rounded(self):
        Company.objects.filter(pk=self.company.pk).update(discount_bps=500)
        self.assertEqual(self.purchase().total_minor,11400)
    def test_threshold_requires_approval(self):
        order=self.purchase(5)
        self.assertEqual(order.status,"awaiting_approval")
        self.assertFalse(OutboxEvent.objects.filter(order=order).exists())
        s.approve_order(self.users["manager"],order.pk)
        self.assertEqual(OutboxEvent.objects.filter(order=order).count(),1)
    def test_buyer_cannot_approve(self):
        order=self.purchase(5)
        self.assertError("forbidden",s.approve_order,self.users["buyer"],order.pk)
    def test_manager_cannot_self_approve(self):
        order=self.purchase(5,who="manager")
        self.assertError("self_approval",s.approve_order,self.users["manager"],order.pk)
    def test_expired_order_cannot_be_approved(self):
        order=self.purchase(5)
        Order.objects.filter(pk=order.pk).update(reservation_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertError("reservation_expired",s.approve_order,self.users["manager"],order.pk)
    def test_expiry_releases_stock_and_credit_once(self):
        order=self.purchase()
        Order.objects.filter(pk=order.pk).update(reservation_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertTrue(s.expire_order(order.pk));self.assertFalse(s.expire_order(order.pk))
        self.stock.refresh_from_db();self.company.refresh_from_db()
        self.assertEqual((self.stock.reserved,self.company.credit_used_minor),(0,0))
    def test_cancel_confirmed_voids_invoice_and_releases_commitments(self):
        order=self.confirmed()
        s.cancel_order(self.users["buyer"],order.pk,"Purchase no longer needed")
        s.cancel_order(self.users["buyer"],order.pk,"Repeated cancellation request")
        self.stock.refresh_from_db();self.company.refresh_from_db()
        self.assertEqual((self.stock.reserved,self.company.credit_used_minor),(0,0))
        order.invoice.refresh_from_db();self.assertEqual(order.invoice.status,"void")
    def test_paid_order_cannot_be_cancelled(self):
        order=self.confirmed();s.record_payment(self.users["finance"],order.invoice.pk,"PAYMENT-001")
        self.assertError("paid_order",s.cancel_order,self.users["buyer"],order.pk,"Please cancel this purchase")
    def test_cannot_ship_before_pack(self):
        order=self.confirmed()
        self.assertError("invalid_transition",s.fulfill_order,self.users["warehouse"],order.pk,"ship")
    def test_shipping_moves_stock_exactly_once(self):
        order=self.confirmed(2)
        s.fulfill_order(self.users["warehouse"],order.pk,"pack")
        s.fulfill_order(self.users["warehouse"],order.pk,"ship")
        s.fulfill_order(self.users["warehouse"],order.pk,"ship")
        self.stock.refresh_from_db()
        self.assertEqual((self.stock.on_hand,self.stock.reserved,Shipment.objects.count()),(18,0,1))
    def test_buyer_cannot_fulfill(self):
        order=self.confirmed();self.assertError("forbidden",s.fulfill_order,self.users["buyer"],order.pk,"pack")
    def test_stock_adjustment_preserves_reservations(self):
        self.purchase(2)
        self.assertError("reserved_stock",s.adjust_stock,self.users["warehouse"],self.stock.pk,-19,"Damaged inventory")
        self.stock.refresh_from_db();self.assertEqual(self.stock.on_hand,20)
    def test_stock_adjustment_records_ledger(self):
        s.adjust_stock(self.users["warehouse"],self.stock.pk,5,"Supplier delivery receipt")
        self.stock.refresh_from_db();self.assertEqual(self.stock.on_hand,25)
        self.assertEqual(StockMovement.objects.get(kind="adjust").on_hand_delta,5)
    def test_payment_releases_credit_once(self):
        order=self.confirmed()
        for _ in range(2): s.record_payment(self.users["finance"],order.invoice.pk,"PAYMENT-001")
        self.company.refresh_from_db();self.assertEqual(self.company.credit_used_minor,0)
        self.assertEqual(Payment.objects.count(),1)
    def test_payment_reference_cannot_be_reused(self):
        first=self.confirmed();second=self.confirmed()
        s.record_payment(self.users["finance"],first.invoice.pk,"PAYMENT-001")
        self.assertError("payment_conflict",s.record_payment,self.users["finance"],second.invoice.pk,"PAYMENT-001")
    def test_buyer_cannot_record_payment(self):
        order=self.confirmed();self.assertError("forbidden",s.record_payment,self.users["buyer"],order.invoice.pk,"PAYMENT-001")
    def test_return_requires_paid_delivered_order(self):
        order=self.delivered()
        self.assertError("invalid_transition",s.request_return,self.users["buyer"],order.pk,"Equipment no longer needed")
    def test_full_return_restock_refund_is_idempotent(self):
        order=self.paid_delivered()
        case=s.request_return(self.users["buyer"],order.pk,"Equipment no longer needed")
        for _ in range(2): s.receive_return(self.users["warehouse"],case.pk)
        for _ in range(2): s.record_refund(self.users["finance"],case.pk,"REFUND-001")
        self.stock.refresh_from_db();order.refresh_from_db();self.company.refresh_from_db()
        self.assertEqual((self.stock.on_hand,self.stock.reserved,self.company.credit_used_minor),(20,0,0))
        self.assertEqual(order.status,"refunded");self.assertEqual(Refund.objects.count(),1)
    def test_refund_before_warehouse_receipt_rejected(self):
        order=self.paid_delivered()
        case=s.request_return(self.users["buyer"],order.pk,"Wrong item received")
        self.assertError("invalid_transition",s.record_refund,self.users["finance"],case.pk,"REFUND-001")
    def test_foreign_product_and_warehouse_rejected(self):
        self.assertError("not_found",s.set_cart_item,self.users["buyer"],self.foreign_product.pk,1)
        s.set_cart_item(self.users["buyer"],self.product.pk,1)
        self.assertError("not_found",s.checkout,self.users["buyer"],self.foreign_warehouse.pk,
            "100 Market Street, Receiving Bay A",s.cart_data(self.users["buyer"])["version"],"foreign-warehouse-key")
    def test_cross_tenant_finance_and_inventory_rejected(self):
        order=self.confirmed()
        self.assertError("not_found",s.record_payment,self.rival,order.invoice.pk,"RIVAL-PAYMENT")
        self.assertError("not_found",s.adjust_stock,self.rival,self.stock.pk,1,"Foreign inventory change")
    def test_buyer_cannot_read_other_buyers_order(self):
        order=self.purchase(who="buyer2")
        self.assertError("not_found",s.order_for,s.member_for(self.users["buyer"]),order.pk)
    def test_quantities_reject_bool_negative_and_fraction(self):
        for value in (True,-1,1.5,1001,"2"):
            self.assertError("invalid_input",s.set_cart_item,self.users["buyer"],self.product.pk,value)
    def test_stock_constraint_prevents_overreservation(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            Stock.objects.filter(pk=self.stock.pk).update(reserved=21)

class WorkerRules(BusinessFixture,TestCase):
    def test_reconciliation_passes_for_business_workflow(self):
        self.paid_delivered()
        output=StringIO()
        call_command("reconcile",stdout=output)
        self.assertTrue(json.loads(output.getvalue())["passed"])
    def test_reconciliation_detects_credit_drift(self):
        self.purchase()
        Company.objects.filter(pk=self.company.pk).update(credit_used_minor=1)
        output=StringIO()
        with self.assertRaises(CommandError): call_command("reconcile",stdout=output)
        self.assertEqual(json.loads(output.getvalue())["issues"][0]["check"],"credit")
    @override_settings(ENV="production",ENABLE_DEMO=True)
    def test_incident_injection_refused_in_production(self):
        with self.assertRaises(CommandError): call_command("lab_scenario","prepare",stdout=StringIO())
    def test_worker_creates_invoice_and_notification(self):
        order=self.purchase();self.assertTrue(worker.process_one())
        order.refresh_from_db()
        self.assertEqual(order.status,"confirmed")
        self.assertEqual(Invoice.objects.count(),1);self.assertEqual(Notification.objects.count(),1)
    def test_claim_has_exclusive_lease(self):
        self.purchase();claim=worker.claim_event();self.assertIsNotNone(claim)
        self.assertIsNone(worker.claim_event())
    def test_wrong_ownership_token_cannot_commit(self):
        self.purchase();event_id,token=worker.claim_event()
        self.assertFalse(worker.process_event(event_id,uuid.uuid4()))
        self.assertEqual(Invoice.objects.count(),0)
    def test_expired_lease_recovery_rejects_old_owner(self):
        self.purchase();event_id,oldtoken=worker.claim_event()
        OutboxEvent.objects.filter(pk=event_id).update(lease_until=timezone.now()-timedelta(seconds=1))
        _,newtoken=worker.claim_event();self.assertNotEqual(oldtoken,newtoken)
        self.assertFalse(worker.process_event(event_id,oldtoken))
        self.assertTrue(worker.process_event(event_id,newtoken));self.assertEqual(Invoice.objects.count(),1)
    def test_completed_job_reprocessing_creates_no_duplicate_effects(self):
        order=self.purchase();worker.process_one()
        OutboxEvent.objects.filter(order=order).update(status="pending")
        worker.process_one()
        self.assertEqual(Invoice.objects.count(),1);self.assertEqual(Notification.objects.count(),1)
    @override_settings(WORKER_FAIL_KIND="order.accepted")
    def test_failure_rolls_back_effects_and_schedules_retry(self):
        self.purchase();worker.process_one()
        job=OutboxEvent.objects.get()
        self.assertEqual(job.status,"retry");self.assertEqual(job.attempts,1)
        self.assertGreater(job.available_at,timezone.now())
        self.assertEqual(Invoice.objects.count(),0)
    def test_dead_letter_and_authorized_replay_recover(self):
        order=self.purchase()
        with override_settings(WORKER_FAIL_KIND="order.accepted",MAX_JOB_ATTEMPTS=2):
            worker.process_one()
            OutboxEvent.objects.update(available_at=timezone.now()-timedelta(seconds=1))
            worker.process_one()
        job=OutboxEvent.objects.get();self.assertEqual(job.status,"dead")
        self.assertError("forbidden",s.retry_event,self.users["buyer"],job.pk)
        s.retry_event(self.users["operator"],job.pk)
        worker.process_one();job.refresh_from_db()
        self.assertEqual(job.status,"done");self.assertEqual(Invoice.objects.count(),1)
        self.assertTrue(AuditEvent.objects.filter(action="outbox.replayed").exists())
    def test_cancelled_order_is_not_invoiced(self):
        order=self.purchase();s.cancel_order(self.users["buyer"],order.pk,"No longer required")
        worker.process_one();self.assertEqual(Invoice.objects.count(),0)
    def test_expired_order_is_released_not_invoiced(self):
        order=self.purchase()
        Order.objects.filter(pk=order.pk).update(reservation_expires_at=timezone.now()-timedelta(seconds=1))
        worker.process_one();order.refresh_from_db();self.stock.refresh_from_db()
        self.assertEqual(order.status,"cancelled");self.assertEqual(self.stock.reserved,0)
        self.assertEqual(Invoice.objects.count(),0)

class WebSecurity(BusinessFixture,TestCase):
    def setUp(self): self.client.force_login(self.users["buyer"])
    def post(self,url,data,**kwargs):
        return self.client.post(url,json.dumps(data),content_type="application/json",**kwargs)
    def test_all_workspace_pages_render_for_operator(self):
        self.paid_delivered()
        self.client.force_login(self.users["operator"])
        for path in ("/","/catalog/","/orders/","/approvals/","/fulfillment/","/inventory/","/finance/","/returns/","/operations/","/audit/","/notifications/"):
            with self.subTest(path=path): self.assertEqual(self.client.get(path).status_code,200)
    def test_order_detail_renders_state_actions(self):
        order=self.confirmed()
        response=self.client.get(f"/orders/{order.pk}/")
        self.assertEqual(response.status_code,200);self.assertContains(response,order.number)
    def test_restricted_pages_return_403_not_500(self):
        for path in ("/approvals/","/fulfillment/","/inventory/","/finance/","/operations/","/audit/"):
            with self.subTest(path=path): self.assertEqual(self.client.get(path).status_code,403)
    def test_foreign_order_returns_404_in_html_and_api(self):
        order=self.purchase();self.client.force_login(self.rival)
        self.assertEqual(self.client.get(f"/orders/{order.pk}/").status_code,404)
        self.assertEqual(self.client.get(f"/api/orders/{order.pk}/").status_code,404)
    def test_catalog_hides_foreign_products(self):
        response=self.client.get("/catalog/")
        self.assertContains(response,"Network switch");self.assertNotContains(response,"Foreign router")
    def test_anonymous_api_is_401_and_html_redirects(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/cart/").status_code,401)
        self.assertEqual(self.client.get("/orders/").status_code,302)
    def test_csrf_enforced_on_mutation(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.users["buyer"])
        response=client.post("/api/cart/",json.dumps({"product_id":self.product.pk,"quantity":1}),content_type="application/json")
        self.assertEqual(response.status_code,403)
        client.get("/catalog/");token=client.cookies["csrftoken"].value
        response=client.post("/api/cart/",json.dumps({"product_id":self.product.pk,"quantity":1}),content_type="application/json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200)
    def test_checkout_replay_over_http(self):
        self.post("/api/cart/",{"product_id":self.product.pk,"quantity":1})
        version=self.client.get("/api/cart/").json()["version"]
        data={"warehouse_id":self.warehouse.pk,"shipping_address":"100 Market Street, Receiving Bay A","cart_version":version}
        first=self.post("/api/checkout/",data,HTTP_IDEMPOTENCY_KEY="http-checkout-001")
        second=self.post("/api/checkout/",data,HTTP_IDEMPOTENCY_KEY="http-checkout-001")
        self.assertEqual((first.status_code,second.status_code),(201,200))
        self.assertEqual(first.json()["id"],second.json()["id"])
    def test_unknown_fields_do_not_allow_price_tampering(self):
        response=self.post("/api/cart/",{"product_id":self.product.pk,"quantity":1,"price":1})
        self.assertEqual(response.status_code,400)
    def test_metrics_require_bearer_token(self):
        self.assertEqual(self.client.get("/metrics").status_code,401)
        response=self.client.get("/metrics",HTTP_AUTHORIZATION="Bearer test-metrics-token")
        self.assertEqual(response.status_code,200);self.assertContains(response,"harborcart_queue_oldest_seconds")
    def test_readiness_reports_database_failure(self):
        with patch("commerce.views.Company.objects.exists",side_effect=DatabaseError("secret")):
            response=self.client.get("/readyz")
        self.assertEqual(response.status_code,503);self.assertNotContains(response,"secret",status_code=503)
        self.assertEqual(self.client.get("/healthz").status_code,200)
    def test_security_headers_present(self):
        response=self.client.get("/")
        for key in ("Content-Security-Policy","X-Content-Type-Options","X-Frame-Options","X-Request-ID"):
            self.assertIn(key,response.headers)
    def test_login_throttle(self):
        self.client.logout()
        for _ in range(10): self.client.post("/login/",{"username":"buyer","password":"incorrect"})
        self.assertEqual(self.client.post("/login/",{"username":"buyer","password":"incorrect"}).status_code,429)
    def test_product_name_is_html_escaped(self):
        Product.objects.filter(pk=self.product.pk).update(name="<script>alert(1)</script>")
        response=self.client.get("/catalog/")
        self.assertContains(response,"&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response,"<script>alert(1)</script>")
    def test_notification_cannot_be_read_by_foreign_user(self):
        self.confirmed();notice=Notification.objects.get()
        self.client.force_login(self.rival)
        self.assertEqual(self.post(f"/api/notifications/{notice.pk}/read/",{}).status_code,404)
