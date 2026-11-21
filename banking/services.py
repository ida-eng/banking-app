"""Banking operations. Every balance change goes through here, inside a DB transaction."""
import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from . import iban as ibanlib
from .models import Account, Transaction, new_transfer_id

TWO_PLACES = Decimal("0.01")
MAX_TRANSFER = Decimal("10000.00")


class TransferError(Exception):
    """Raised when a transfer cannot be made; the message is safe to show to the user."""


@dataclass
class TransferResult:
    debit: Transaction
    credit: Transaction | None
    internal: bool


def to_money(value) -> Decimal:
    amount = Decimal(str(value))
    if amount != amount.quantize(TWO_PLACES):
        raise TransferError("Amounts can have at most two decimal places.")
    return amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def open_account(user, name, kind=Account.Kind.CURRENT, opening_balance=Decimal("0.00")):
    """Create an account with a unique, checksum-valid IBAN."""
    while True:
        candidate = ibanlib.generate_albanian()
        if not Account.objects.filter(iban=candidate).exists():
            break
    account = Account.objects.create(user=user, name=name, kind=kind, iban=candidate)
    if opening_balance > 0:
        deposit(account, opening_balance, "Opening deposit", category=Transaction.Category.TRANSFER)
    return account


@db_transaction.atomic
def deposit(account, amount, description, category=Transaction.Category.OTHER, when=None, counterparty_name=""):
    amount = to_money(amount)
    locked = Account.objects.select_for_update().get(pk=account.pk)
    locked.balance += amount
    locked.save(update_fields=["balance"])
    account.balance = locked.balance
    return Transaction.objects.create(
        account=locked, kind=Transaction.Kind.CREDIT, amount=amount, balance_after=locked.balance,
        category=category, description=description, counterparty_name=counterparty_name,
        created_at=when or timezone.now(),
    )


@db_transaction.atomic
def withdraw(account, amount, description, category=Transaction.Category.OTHER, when=None, counterparty_name=""):
    amount = to_money(amount)
    locked = Account.objects.select_for_update().get(pk=account.pk)
    if amount > locked.balance:
        raise TransferError("Insufficient funds.")
    locked.balance -= amount
    locked.save(update_fields=["balance"])
    account.balance = locked.balance
    return Transaction.objects.create(
        account=locked, kind=Transaction.Kind.DEBIT, amount=amount, balance_after=locked.balance,
        category=category, description=description, counterparty_name=counterparty_name,
        created_at=when or timezone.now(),
    )


def transfer(*, source, to_iban, amount, beneficiary_name="", reference="", category=Transaction.Category.TRANSFER):
    """Send money from `source` to any valid IBAN.

    If the IBAN belongs to an account in this bank, the money is credited there in the
    same database transaction (an internal transfer); otherwise it leaves as a SEPA payment.
    """
    try:
        target_iban = ibanlib.validate(to_iban)
    except ibanlib.IBANError as exc:
        raise TransferError(str(exc)) from exc

    amount = to_money(amount)
    if amount <= 0:
        raise TransferError("Enter an amount greater than zero.")
    if amount > MAX_TRANSFER:
        raise TransferError(f"The daily limit for a single transfer is €{MAX_TRANSFER:,.2f}.")
    if target_iban == source.iban:
        raise TransferError("You can't send money to the same account.")

    with db_transaction.atomic():
        # Lock both rows in a fixed order (by primary key) so two opposite transfers can't deadlock.
        destination = Account.objects.filter(iban=target_iban).first()
        ids = sorted({source.pk} | ({destination.pk} if destination else set()))
        locked = {a.pk: a for a in Account.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
        src = locked[source.pk]
        dst = locked.get(destination.pk) if destination else None

        if amount > src.balance:
            raise TransferError(f"Insufficient funds. Available balance is €{src.balance:,.2f}.")

        transfer_id = new_transfer_id()
        now = timezone.now()
        name = beneficiary_name.strip()
        if not name and dst:
            name = dst.name if dst.user_id == src.user_id else (dst.user.get_full_name() or dst.user.username)

        src.balance -= amount
        src.save(update_fields=["balance"])
        debit = Transaction.objects.create(
            account=src, kind=Transaction.Kind.DEBIT, amount=amount, balance_after=src.balance,
            category=category, description=f"Transfer to {name}" if name else "Transfer",
            counterparty_name=name, counterparty_iban=target_iban, reference=reference.strip(),
            transfer_id=transfer_id, created_at=now,
        )

        credit = None
        if dst:
            dst.balance += amount
            dst.save(update_fields=["balance"])
            sender = src.user.get_full_name() or src.user.username
            credit = Transaction.objects.create(
                account=dst, kind=Transaction.Kind.CREDIT, amount=amount, balance_after=dst.balance,
                category=Transaction.Category.TRANSFER,
                description=f"Transfer from {sender}" if dst.user_id != src.user_id else f"From {src.name}",
                counterparty_name=sender, counterparty_iban=src.iban, reference=reference.strip(),
                transfer_id=transfer_id, created_at=now,
            )

    source.balance = src.balance
    return TransferResult(debit=debit, credit=credit, internal=dst is not None)


# ---------- demo data ----------
MERCHANTS = [
    ("Spar Albania", Transaction.Category.GROCERIES, (12, 85)),
    ("Conad", Transaction.Category.GROCERIES, (8, 60)),
    ("Mulliri Vjetër", Transaction.Category.DINING, (3, 14)),
    ("Komiteti Kafe", Transaction.Category.DINING, (6, 32)),
    ("Uber", Transaction.Category.TRANSPORT, (4, 18)),
    ("Tirana Bus Card", Transaction.Category.TRANSPORT, (10, 10)),
    ("Zara TEG", Transaction.Category.SHOPPING, (25, 120)),
    ("Neptun", Transaction.Category.SHOPPING, (30, 240)),
    ("Netflix", Transaction.Category.ENTERTAINMENT, (12, 12)),
    ("Spotify", Transaction.Category.ENTERTAINMENT, (11, 11)),
    ("Kino Millennium", Transaction.Category.ENTERTAINMENT, (5, 16)),
    ("Farmacia Tirana", Transaction.Category.HEALTH, (6, 45)),
]


def seed_history(account, savings=None, months=4, rng=None):
    """Fill an account with a realistic few months of activity."""
    rng = rng or random.Random(account.pk)
    now = timezone.now()
    start = now - timedelta(days=30 * months)
    day = start
    events = []
    while day < now:
        if day.day == 1:
            events.append((day.replace(hour=9), "credit", Decimal("1450.00"), "Salary · Acme Software", Transaction.Category.SALARY, "Acme Software"))
            events.append((day.replace(hour=11), "debit", Decimal("420.00"), "Rent · Rr. e Durrësit", Transaction.Category.RENT, "Landlord"))
        if day.day == 5:
            events.append((day.replace(hour=10), "debit", Decimal("38.50"), "OSHEE electricity", Transaction.Category.RENT, "OSHEE"))
            events.append((day.replace(hour=10, minute=5), "debit", Decimal("24.00"), "Vodafone Albania", Transaction.Category.RENT, "Vodafone"))
        for _ in range(rng.choice((0, 1, 1, 2))):
            merchant, cat, (lo, hi) = rng.choice(MERCHANTS)
            amount = Decimal(str(round(rng.uniform(lo, hi), 2)))
            hour = rng.randint(8, 21)
            events.append((day.replace(hour=hour, minute=rng.randint(0, 59)), "debit", amount, merchant, cat, merchant))
        day += timedelta(days=1)

    for when, kind, amount, desc, cat, who in sorted(events, key=lambda e: e[0]):
        if when > now:
            continue
        try:
            if kind == "credit":
                deposit(account, amount, desc, category=cat, when=when, counterparty_name=who)
            else:
                withdraw(account, amount, desc, category=cat, when=when, counterparty_name=who)
        except TransferError:
            continue
        if savings and kind == "credit" and cat == Transaction.Category.SALARY:
            moved = when + timedelta(seconds=30)
            withdraw(account, Decimal("200.00"), f"To {savings.name}", category=Transaction.Category.TRANSFER, when=moved)
            deposit(savings, Decimal("200.00"), f"From {account.name}", category=Transaction.Category.TRANSFER, when=moved)
