import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import BeneficiaryForm, SignUpForm, TransactionFilterForm, TransferForm
from .models import Account, Beneficiary, Transaction

DEMO_USERNAME = "demo"


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        current = services.open_account(user, "Everyday", Account.Kind.CURRENT, Decimal("1000.00"))
        services.open_account(user, "Savings", Account.Kind.SAVINGS, Decimal("2500.00"))
        login(request, user)
        messages.success(request, f"Welcome, {user.first_name}! Your accounts are ready, with €3,500 of demo money.")
        return redirect("account", pk=current.pk)
    return render(request, "registration/signup.html", {"form": form})


@require_POST
def demo_login(request):
    user = User.objects.filter(username=DEMO_USERNAME).first()
    if user is None:
        from django.core.management import call_command

        call_command("seed_demo")
        user = User.objects.get(username=DEMO_USERNAME)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.info(request, "You're using the shared demo account. Feel free to try a transfer.")
    return redirect("dashboard")


def _transactions_for(user):
    return Transaction.objects.filter(account__user=user).select_related("account")


@login_required
def dashboard(request):
    accounts = list(request.user.accounts.all())
    total = sum((a.balance for a in accounts), Decimal("0"))
    txs = _transactions_for(request.user)
    now = timezone.now()

    own_ibans = [a.iban for a in accounts]
    month_start = timezone.localtime(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = (
        txs.filter(created_at__gte=month_start)
        .exclude(counterparty_iban__in=own_ibans)
        .exclude(category=Transaction.Category.TRANSFER, counterparty_iban="")
    )
    money_in = this_month.filter(kind="credit").aggregate(s=Sum("amount"))["s"] or Decimal("0")
    money_out = this_month.filter(kind="debit").aggregate(s=Sum("amount"))["s"] or Decimal("0")

    # Spending by category, last 30 days (internal moves between own accounts excluded)
    spend = (
        txs.filter(kind="debit", created_at__gte=now - timedelta(days=30))
        .exclude(counterparty_iban__in=own_ibans)
        .exclude(category=Transaction.Category.TRANSFER, counterparty_iban="")
        .values("category").annotate(total=Sum("amount")).order_by("-total")
    )
    labels = dict(Transaction.Category.choices)
    by_category = [{"label": labels[r["category"]], "total": float(r["total"])} for r in spend]

    # Money in / out for the last 6 months
    six = timezone.localtime(now - timedelta(days=183)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly = {}
    rows = (
        txs.filter(created_at__gte=six).exclude(counterparty_iban__in=own_ibans)
        .exclude(category=Transaction.Category.TRANSFER, counterparty_iban="")
        .annotate(m=TruncMonth("created_at")).values("m", "kind").annotate(total=Sum("amount")).order_by("m")
    )
    for r in rows:
        key = r["m"].strftime("%b")
        monthly.setdefault(key, {"month": key, "in": 0.0, "out": 0.0})
        monthly[key]["in" if r["kind"] == "credit" else "out"] = float(r["total"])

    return render(request, "banking/dashboard.html", {
        "accounts": accounts,
        "total": total,
        "money_in": money_in,
        "money_out": money_out,
        "recent": txs[:8],
        "by_category": by_category,
        "monthly": list(monthly.values()),
        "is_demo": request.user.username == DEMO_USERNAME,
    })


def _filtered(account, params):
    form = TransactionFilterForm(params or None)
    qs = account.transactions.all()
    if form.is_valid():
        d = form.cleaned_data
        if d["q"]:
            qs = qs.filter(Q(description__icontains=d["q"]) | Q(counterparty_name__icontains=d["q"]) | Q(reference__icontains=d["q"]))
        if d["kind"]:
            qs = qs.filter(kind=d["kind"])
        if d["category"]:
            qs = qs.filter(category=d["category"])
        if d["date_from"]:
            qs = qs.filter(created_at__date__gte=d["date_from"])
        if d["date_to"]:
            qs = qs.filter(created_at__date__lte=d["date_to"])
    return form, qs


@login_required
def account_detail(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    form, qs = _filtered(account, request.GET)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "banking/account.html", {
        "account": account,
        "accounts": request.user.accounts.all(),
        "form": form,
        "page": page,
        "querystring": params.urlencode(),
        "count": qs.count(),
    })


@login_required
def statement_csv(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    _, qs = _filtered(account, request.GET)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="statement-{account.iban[-4:]}-{timezone.localdate()}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Description", "Category", "Counterparty", "Counterparty IBAN", "Reference", "Amount", "Balance"])
    for t in qs.order_by("created_at"):
        writer.writerow([
            timezone.localtime(t.created_at).strftime("%Y-%m-%d %H:%M"), t.description, t.get_category_display(),
            t.counterparty_name, t.counterparty_iban, t.reference, f"{t.signed_amount:.2f}", f"{t.balance_after:.2f}",
        ])
    return response


@login_required
def transfer(request):
    initial = {}
    if "from" in request.GET:
        initial["source"] = request.GET["from"]
    form = TransferForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            result = services.transfer(
                source=d["source"], to_iban=d["to_iban"], amount=d["amount"],
                beneficiary_name=d["beneficiary_name"], reference=d["reference"], category=d["category"],
            )
        except services.TransferError as exc:
            form.add_error(None, str(exc))
        else:
            if d.get("save_beneficiary") and not d.get("beneficiary") and not request.user.accounts.filter(iban=d["to_iban"]).exists():
                Beneficiary.objects.get_or_create(user=request.user, iban=d["to_iban"], defaults={"name": d["beneficiary_name"]})
            how = "instantly" if result.internal else "via SEPA"
            messages.success(request, f"€{d['amount']:,.2f} sent to {result.debit.counterparty_name or 'recipient'} {how}.")
            return redirect("account", pk=d["source"].pk)
    return render(request, "banking/transfer.html", {
        "form": form,
        "accounts": request.user.accounts.all(),
        "beneficiaries": request.user.beneficiaries.all(),
    })


@login_required
def beneficiaries(request):
    form = BeneficiaryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if request.user.beneficiaries.filter(iban=form.cleaned_data["iban"]).exists():
            form.add_error("iban", "You already saved this IBAN.")
        else:
            b = form.save(commit=False)
            b.user = request.user
            b.save()
            messages.success(request, f"{b.name} was added to your recipients.")
            return redirect("beneficiaries")
    return render(request, "banking/beneficiaries.html", {"form": form, "items": request.user.beneficiaries.all()})


@login_required
@require_POST
def beneficiary_delete(request, pk):
    b = get_object_or_404(Beneficiary, pk=pk, user=request.user)
    b.delete()
    messages.info(request, f"{b.name} was removed.")
    return redirect("beneficiaries")
