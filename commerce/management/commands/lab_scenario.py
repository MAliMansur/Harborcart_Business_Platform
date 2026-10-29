"""Local-only incident facilitator. Read the scenario brief before this source."""
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from commerce import services as s
from commerce.models import Cart, Company, Order, OutboxEvent, Product, Warehouse

class Command(BaseCommand):
    help="Prepare or repair the HC-01 exercise in fictional local demo data."
    def add_arguments(self,parser):
        parser.add_argument("action",choices=["prepare","repair"])
        parser.add_argument("--order",default="")
    @transaction.atomic
    def handle(self,**options):
        if settings.ENV!="local" or not settings.ENABLE_DEMO:
            raise CommandError("Incident preparation is restricted to the local fictional demo.")
        company=Company.objects.select_for_update().filter(slug="atlas-supply").first()
        if not company: raise CommandError("Run seed_demo first.")
        if options["action"]=="prepare":
            buyer=get_user_model().objects.get(username="buyer",membership__company=company)
            if Cart.objects.filter(user=buyer,items__isnull=False).exists():
                raise CommandError("Finish or empty the buyer's existing cart before starting this exercise.")
            product=Product.objects.get(company=company,sku="NET-110")
            warehouse=Warehouse.objects.get(company=company,code="EAST")
            s.set_cart_item(buyer,product.pk,1)
            order,_=s.checkout(buyer,warehouse.pk,"100 Training Street, Fictional Receiving Bay",
                s.cart_data(buyer)["version"],"lab-hc01-"+uuid.uuid4().hex)
            if order.status!="queued": raise CommandError("Scenario needs a below-threshold purchase; review the current company policy.")
            job=OutboxEvent.objects.select_for_update().get(order=order,kind="order.accepted")
            job.kind="order.accepted.v0"
            job.save(update_fields=["kind"])
            s.audit(company,None,"lab.scenario_prepared",order,scenario="HC-01")
            self.stdout.write("HC-01 prepared. Investigate order "+str(order.pk))
            self.stdout.write("Keep the worker running. Read docs/drills.md; do not open the solutions yet.")
        else:
            try: order_id=uuid.UUID(options["order"])
            except ValueError: raise CommandError("--order must identify the HC-01 purchase.")
            order=Order.objects.select_for_update().filter(pk=order_id,company=company,idempotency_key__startswith="lab-hc01-").first()
            if not order: raise CommandError("Only an HC-01 exercise order can be repaired.")
            if order.status!="queued": raise CommandError("This purchase is no longer queued; inspect expiry and submit a fresh exercise.")
            job=OutboxEvent.objects.select_for_update().get(order=order,deduplication_key="order.accepted:"+str(order.pk))
            if job.status=="processing": raise CommandError("A worker owns the job. Wait for its bounded attempt to finish.")
            job.kind="order.accepted";job.save(update_fields=["kind"])
            s.audit(company,None,"lab.scenario_repaired",order,scenario="HC-01")
            self.stdout.write("Exercise compatibility repair applied. Replay the failed job as operator, then validate recovery.")
