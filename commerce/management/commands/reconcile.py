import json
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from commerce.models import Company, Invoice, Order, OrderItem, Stock, Payment, Refund

class Command(BaseCommand):
    help="Read-only consistency check of stock reservations, credit, invoices and settlement records."
    def handle(self,**options):
        issues=[];companies=0
        for pk in Company.objects.values_list("pk",flat=True):
            with transaction.atomic():
                company=Company.objects.select_for_update().get(pk=pk)
                companies+=1
                orders=Order.objects.filter(company=company)
                committed=orders.exclude(status__in=["cancelled","refunded"]).exclude(invoice__status="paid")
                expected=committed.aggregate(n=Sum("total_minor"))["n"] or 0
                if expected!=company.credit_used_minor:
                    issues.append({"company_id":pk,"check":"credit","expected":expected,"observed":company.credit_used_minor})
                for stock in Stock.objects.filter(product__company=company):
                    expected=OrderItem.objects.filter(product=stock.product,order__warehouse=stock.warehouse,
                        order__company=company,order__status__in=["awaiting_approval","queued","confirmed","packed"]).aggregate(n=Sum("quantity"))["n"] or 0
                    if expected!=stock.reserved:
                        issues.append({"stock_id":stock.pk,"check":"reserved","expected":expected,"observed":stock.reserved})
                for invoice in Invoice.objects.filter(company=company):
                    if invoice.total_minor!=invoice.order.total_minor:
                        issues.append({"invoice_id":invoice.pk,"check":"invoice_total"})
                    payment=Payment.objects.filter(invoice=invoice).first()
                    if (invoice.status=="paid")!=bool(payment) or (payment and payment.amount_minor!=invoice.total_minor):
                        issues.append({"invoice_id":invoice.pk,"check":"payment"})
                for refund in Refund.objects.filter(company=company).select_related("return_case__order"):
                    if refund.amount_minor!=refund.return_case.order.total_minor or refund.return_case.status!="refunded":
                        issues.append({"refund_id":refund.pk,"check":"refund"})
        self.stdout.write(json.dumps({"companies_checked":companies,"issues":issues,"passed":not issues},indent=2))
        if issues: raise CommandError("Reconciliation failed. Investigate before changing data.")
