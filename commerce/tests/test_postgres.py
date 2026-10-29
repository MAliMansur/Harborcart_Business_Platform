"""Concurrency evidence must run on PostgreSQL, never inferred from SQLite."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from django.db import connection, close_old_connections, connections
from django.test import TransactionTestCase
from commerce import services as s, worker
from commerce.models import Order, Stock, Invoice, OutboxEvent
from .test_business import BusinessFixture

@unittest.skipUnless(connection.vendor=="postgresql","PostgreSQL required for row-lock concurrency tests")
class PostgreSQLConcurrency(BusinessFixture,TransactionTestCase):
    def setUp(self): self.setUpTestData()
    def race(self,functions):
        barrier=threading.Barrier(len(functions))
        def run(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return fn()
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures=[pool.submit(run,fn) for fn in functions]
            return [future.result(timeout=25) for future in futures]
    def test_competing_checkout_cannot_oversell_last_unit(self):
        Stock.objects.filter(pk=self.stock.pk).update(on_hand=1)
        versions={}
        for name in ("buyer","buyer2"):
            s.set_cart_item(self.users[name],self.product.pk,1)
            versions[name]=s.cart_data(self.users[name])["version"]
        def checkout(name):
            try:
                s.checkout(self.users[name],self.warehouse.pk,"100 Market Street, Receiving Bay A",
                    versions[name],"concurrency-"+name)
                return "accepted"
            except s.BusinessError as e: return e.code
        results=self.race([lambda:checkout("buyer"),lambda:checkout("buyer2")])
        self.assertCountEqual(results,["accepted","insufficient_stock"])
        self.stock.refresh_from_db();self.assertEqual(self.stock.reserved,1)
        self.assertEqual(Order.objects.count(),1)
    def test_concurrent_same_key_commits_one_order(self):
        s.set_cart_item(self.users["buyer"],self.product.pk,1)
        version=s.cart_data(self.users["buyer"])["version"]
        def checkout():
            return s.checkout(self.users["buyer"],self.warehouse.pk,"100 Market Street, Receiving Bay A",
                version,"concurrent-same-key")[0].pk
        result=self.race([checkout,checkout])
        self.assertEqual(result[0],result[1]);self.assertEqual(Order.objects.count(),1)
        self.stock.refresh_from_db();self.assertEqual(self.stock.reserved,1)
    def test_competing_workers_do_not_duplicate_invoice(self):
        self.purchase()
        self.race([worker.process_one,worker.process_one])
        self.assertEqual(Invoice.objects.count(),1)
        self.assertEqual(OutboxEvent.objects.filter(status="done").count(),1)
