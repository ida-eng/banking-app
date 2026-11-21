import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from . import iban as ibanlib


class Account(models.Model):
    class Kind(models.TextChoices):
        CURRENT = "current", "Current account"
        SAVINGS = "savings", "Savings account"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CURRENT)
    iban = models.CharField(max_length=34, unique=True)
    currency = models.CharField(max_length=3, default="EUR")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "created_at"]

    def __str__(self):
        return f"{self.name} ({self.iban_display})"

    @property
    def iban_display(self):
        return ibanlib.pretty(self.iban)

    @property
    def iban_masked(self):
        return f"•••• {self.iban[-4:]}"


class Transaction(models.Model):
    class Kind(models.TextChoices):
        CREDIT = "credit", "Money in"
        DEBIT = "debit", "Money out"

    class Category(models.TextChoices):
        SALARY = "salary", "Salary"
        TRANSFER = "transfer", "Transfer"
        GROCERIES = "groceries", "Groceries"
        RENT = "rent", "Rent & bills"
        DINING = "dining", "Dining"
        TRANSPORT = "transport", "Transport"
        SHOPPING = "shopping", "Shopping"
        ENTERTAINMENT = "entertainment", "Entertainment"
        HEALTH = "health", "Health"
        OTHER = "other", "Other"

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField(max_length=140)
    counterparty_name = models.CharField(max_length=70, blank=True)
    counterparty_iban = models.CharField(max_length=34, blank=True)
    reference = models.CharField(max_length=140, blank=True)
    transfer_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        sign = "+" if self.kind == self.Kind.CREDIT else "-"
        return f"{sign}{self.amount} {self.description}"

    @property
    def signed_amount(self):
        return self.amount if self.kind == self.Kind.CREDIT else -self.amount


class Beneficiary(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beneficiaries")
    name = models.CharField(max_length=70)
    iban = models.CharField(max_length=34)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["user", "iban"], name="unique_beneficiary_per_user")]

    def __str__(self):
        return f"{self.name} ({self.iban})"

    @property
    def iban_display(self):
        return ibanlib.pretty(self.iban)


def new_transfer_id():
    return uuid.uuid4()
