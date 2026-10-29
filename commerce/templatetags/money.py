from decimal import Decimal
from django import template
register=template.Library()
@register.filter
def money(value):
    return f"{Decimal(int(value or 0))/100:,.2f}"
@register.filter
def label(value):
    return str(value).replace("_"," ").title()
