from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from banking import services
from banking.models import Account, Beneficiary


class Command(BaseCommand):
    help = "Create (or reset) the shared demo user with a few months of realistic activity."

    @transaction.atomic
    def handle(self, *args, **options):
        User.objects.filter(username="demo").delete()
        user = User.objects.create_user("demo", "demo@example.com", "demo-password-123", first_name="Demo", last_name="User")
        months = 5
        opened = timezone.now() - timedelta(days=30 * months + 1)
        current = services.open_account(user, "Everyday", Account.Kind.CURRENT)
        savings = services.open_account(user, "Savings", Account.Kind.SAVINGS)
        # Date the opening deposits before the history so the timeline and running balances line up
        services.deposit(current, Decimal("600.00"), "Opening deposit", category="transfer", when=opened)
        services.deposit(savings, Decimal("1800.00"), "Opening deposit", category="transfer", when=opened)
        services.seed_history(current, savings=savings, months=months)
        Beneficiary.objects.create(user=user, name="Olivia Bennett", iban="AL35202111090000000001234567")
        Beneficiary.objects.create(user=user, name="Studio Mila GmbH", iban="DE89370400440532013000")
        self.stdout.write(self.style.SUCCESS(f"Demo user ready: {current.balance} / {savings.balance}"))
