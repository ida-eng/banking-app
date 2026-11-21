from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def money(value):
    """1234.5 -> €1,234.50 ; -12 -> −€12.00"""
    if value in (None, ""):
        return ""
    v = Decimal(str(value))
    sign = "−" if v < 0 else ""
    return f"{sign}€{abs(v):,.2f}"
