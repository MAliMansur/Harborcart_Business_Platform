import os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from commerce import services as s
from commerce.models import Company, Membership, Product, Warehouse, Stock
from commerce.worker import process_one, heartbeat

PRODUCTS = [
    ("NET-240","Managed network switch","Networking",18900,"24-port gigabit switch for branch installations."),
    ("NET-610","Wi-Fi access point","Networking",12900,"Ceiling-mounted wireless access point."),
    ("NET-110","Patch cable bundle","Networking",2400,"Ten certified Cat6 cables for rack deployments."),
    ("PWR-900","Rack UPS 1500VA","Power",32900,"Battery backup for network and edge equipment."),
    ("PWR-210","Rack power strip","Power",5900,"Eight-outlet power distribution unit."),
    ("CMP-310","Mini workstation","Compute",49900,"Compact workstation for operations desks."),
    ("CMP-420","Portable SSD 1TB","Compute",8900,"Encrypted-capable portable storage."),
    ("DSP-270","27-inch IPS monitor","Workplace",21900,"QHD display with height-adjustable stand."),
    ("DSP-120","USB-C docking station","Workplace",11900,"Dual-display dock with wired networking."),
    ("WRK-200","Ergonomic keyboard","Workplace",6900,"Split-layout keyboard for shared workstations."),
    ("WRK-105","Conference headset","Workplace",7900,"USB headset with noise-reducing microphone."),
    ("SEC-700","Security key pair","Security",6500,"Two hardware authentication keys."),
    ("SEC-300","Cable lock kit","Security",1900,"Physical locks for desks and equipment."),
    ("TOO-500","Network tool kit","Tools",9900,"Crimper, tester and termination accessories."),
    ("TOO-110","Equipment label pack","Tools",1200,"Durable labels for asset inventory."),
    ("RCK-600","6U wall rack","Networking",15900,"Wall-mount enclosure for branch infrastructure."),
]
class Command(BaseCommand):
    help = "Seed local fictional workspaces once. Never resets existing data."
    @transaction.atomic
    def handle(self, **options):
        if not settings.ENABLE_DEMO or settings.ENV == "production":
            raise CommandError("Demo seeding is disabled.")
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 16: raise CommandError("Run scripts/bootstrap.py first.")
        if Company.objects.filter(slug="atlas-supply").exists():
            self.stdout.write("Demo already exists; no data or passwords changed.")
            return
        company = Company.objects.create(name="Atlas Supply",slug="atlas-supply",
            approval_threshold_minor=50000,credit_limit_minor=5000000,discount_bps=500)
        users = {}
        for username, role in [("buyer","buyer"),("manager","approver"),("warehouse","warehouse"),
                                ("finance","finance"),("operator","admin")]:
            user=get_user_model().objects.create_user(username=username,password=password)
            Membership.objects.create(user=user,company=company,role=role)
            users[username]=user
        warehouses = [Warehouse.objects.create(company=company,code=code,name=name,city=city)
            for code,name,city in [("EAST","East distribution center","Newark"),
                                   ("WEST","West distribution center","Sacramento")]]
        products=[]
        for i,(sku,name,category,price,description) in enumerate(PRODUCTS):
            product=Product.objects.create(company=company,sku=sku,name=name,category=category,
                unit_price_minor=price,description=description)
            products.append(product)
            for j,warehouse in enumerate(warehouses):
                Stock.objects.create(product=product,warehouse=warehouse,on_hand=80+i*7-j*12 if i<13 else 8+j)
        rival=Company.objects.create(name="Boreal Trading",slug="boreal-trading",credit_limit_minor=1000000)
        for username,role in [("rival","buyer"),("rival-manager","approver")]:
            user=get_user_model().objects.create_user(username=username,password=password)
            Membership.objects.create(user=user,company=rival,role=role)
        rw=Warehouse.objects.create(company=rival,code="NORTH",name="Northern warehouse",city="Portland")
        rp=Product.objects.create(company=rival,sku="BOREAL-ONLY",name="Private contract router",
            category="Networking",unit_price_minor=12500,description="Visible only to Boreal Trading.")
        Stock.objects.create(product=rp,warehouse=rw,on_hand=50)
        stages=["refunded","delivered","shipped","packed","confirmed","delivered","cancelled","confirmed"]
        for i,stage in enumerate(stages):
            product=products[i]
            s.set_cart_item(users["buyer"],product.pk,2)
            order,_=s.checkout(users["buyer"],warehouses[i%2].pk,"100 Market Street, Receiving Bay A",
                s.cart_data(users["buyer"])["version"],"demo-order-" + str(i))
            if order.status=="awaiting_approval": s.approve_order(users["manager"],order.pk)
            while process_one(): pass
            if stage=="cancelled":
                s.cancel_order(users["buyer"],order.pk,"Branch procurement request withdrawn")
                continue
            if stage in {"packed","shipped","delivered","refunded"}:
                s.fulfill_order(users["warehouse"],order.pk,"pack")
            if stage in {"shipped","delivered","refunded"}:
                s.fulfill_order(users["warehouse"],order.pk,"ship")
            if stage in {"delivered","refunded"}:
                s.fulfill_order(users["warehouse"],order.pk,"deliver")
                s.record_payment(users["finance"],order.invoice.pk,"DEMO-PAY-" + str(i))
            if stage=="refunded":
                case=s.request_return(users["buyer"],order.pk,"Equipment not required for this branch")
                s.receive_return(users["warehouse"],case.pk)
                s.record_refund(users["finance"],case.pk,"DEMO-REFUND-" + str(i))
            while process_one(): pass
        # Leave genuine operational work for the learner.
        s.set_cart_item(users["buyer"],products[5].pk,2)
        s.checkout(users["buyer"],warehouses[0].pk,"100 Market Street, Receiving Bay A",
            s.cart_data(users["buyer"])["version"],"demo-awaiting-approval")
        s.set_cart_item(users["buyer"],products[2].pk,3)
        s.checkout(users["buyer"],warehouses[0].pk,"100 Market Street, Receiving Bay A",
            s.cart_data(users["buyer"])["version"],"demo-awaiting-worker")
        heartbeat("seed-demo")
        self.stdout.write("Created 2 fictional workspaces, 7 accounts, 17 products and 10 purchases.")
        self.stdout.write("Read .local/demo-credentials.txt. All payments and shipping are sandbox records.")
