from django.contrib import admin

from .models import Account, Beneficiary, Transaction


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "kind", "iban", "balance", "created_at")
    list_filter = ("kind",)
    search_fields = ("iban", "user__username", "name")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "account", "kind", "amount", "balance_after", "category", "description")
    list_filter = ("kind", "category")
    search_fields = ("description", "counterparty_name", "counterparty_iban", "reference")
    date_hierarchy = "created_at"


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ("name", "iban", "user")
