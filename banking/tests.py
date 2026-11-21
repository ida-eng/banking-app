from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from . import iban as ibanlib
from . import services
from .models import Account, Beneficiary, Transaction


class IBANTests(SimpleTestCase):
    def test_valid_ibans(self):
        for value in ["AL47 2121 1009 0000 0002 3569 8741", "DE89 3704 0044 0532 0130 00", "gb29nwbk60161331926819"]:
            self.assertTrue(ibanlib.is_valid(value), value)

    def test_invalid_ibans_explain_why(self):
        with self.assertRaisesMessage(ibanlib.IBANError, "check digits"):
            ibanlib.validate("DE89 3704 0044 0532 0130 01")
        with self.assertRaisesMessage(ibanlib.IBANError, "22 characters"):
            ibanlib.validate("DE89 3704 0044 0532 0130")
        with self.assertRaisesMessage(ibanlib.IBANError, "not supported"):
            ibanlib.validate("ZZ12 3456")

    def test_generated_ibans_are_valid_albanian(self):
        for _ in range(50):
            value = ibanlib.generate_albanian()
            self.assertEqual(len(value), 28)
            self.assertTrue(value.startswith("AL"))
            self.assertTrue(ibanlib.is_valid(value))


class TransferTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-alice-123", first_name="Alice")
        self.bob = User.objects.create_user("bob", password="pw-bob-12345", first_name="Bob")
        self.a1 = services.open_account(self.alice, "Everyday", opening_balance=Decimal("100.00"))
        self.a2 = services.open_account(self.alice, "Savings", Account.Kind.SAVINGS)
        self.b1 = services.open_account(self.bob, "Everyday")

    def test_external_sepa_transfer_debits_only_the_source(self):
        result = services.transfer(source=self.a1, to_iban="DE89370400440532013000", amount="25.50", beneficiary_name="Studio Mila")
        self.a1.refresh_from_db()
        self.assertFalse(result.internal)
        self.assertEqual(self.a1.balance, Decimal("74.50"))
        self.assertEqual(result.debit.balance_after, Decimal("74.50"))
        self.assertEqual(result.debit.counterparty_iban, "DE89370400440532013000")

    def test_internal_transfer_moves_money_between_customers(self):
        result = services.transfer(source=self.a1, to_iban=self.b1.iban, amount=Decimal("40"), reference="Dinner")
        self.a1.refresh_from_db()
        self.b1.refresh_from_db()
        self.assertTrue(result.internal)
        self.assertEqual(self.a1.balance, Decimal("60.00"))
        self.assertEqual(self.b1.balance, Decimal("40.00"))
        self.assertEqual(result.debit.transfer_id, result.credit.transfer_id)
        self.assertEqual(result.credit.reference, "Dinner")

    def test_insufficient_funds_changes_nothing(self):
        with self.assertRaisesMessage(services.TransferError, "Insufficient funds"):
            services.transfer(source=self.a1, to_iban=self.b1.iban, amount="100.01")
        self.a1.refresh_from_db()
        self.b1.refresh_from_db()
        self.assertEqual(self.a1.balance, Decimal("100.00"))
        self.assertEqual(self.b1.balance, Decimal("0.00"))
        self.assertEqual(Transaction.objects.filter(account=self.b1).count(), 0)

    def test_rejects_bad_amounts_and_same_account(self):
        for amount in ["0", "-5", "1.005", "10000.01"]:
            with self.assertRaises(services.TransferError, msg=amount):
                services.transfer(source=self.a1, to_iban=self.b1.iban, amount=amount)
        with self.assertRaises(services.TransferError):
            services.transfer(source=self.a1, to_iban=self.a1.iban, amount="1")

    def test_rejects_invalid_iban(self):
        with self.assertRaisesMessage(services.TransferError, "check digits"):
            services.transfer(source=self.a1, to_iban="DE89370400440532013001", amount="1")


class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("carol", password="pw-carol-123", first_name="Carol")
        self.acc = services.open_account(self.user, "Everyday", opening_balance=Decimal("500.00"))
        self.other = services.open_account(User.objects.create_user("dave", password="x-dave-12345"), "Everyday")

    def test_pages_require_login(self):
        for name in ["dashboard", "transfer", "beneficiaries"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)

    def test_dashboard_and_account_pages_render(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("dashboard")), "€500.00")
        self.assertContains(self.client.get(reverse("account", args=[self.acc.pk])), self.acc.iban_display)

    def test_cannot_view_someone_elses_account(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("account", args=[self.other.pk])).status_code, 404)

    def test_transfer_form_and_saved_recipient(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("transfer"), {
            "source": self.acc.pk, "beneficiary_name": "Erion", "to_iban": "AL35 2021 1109 0000 0000 0123 4567",
            "amount": "12.30", "reference": "Books", "category": "shopping", "save_beneficiary": "on",
        })
        self.assertRedirects(response, reverse("account", args=[self.acc.pk]))
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("487.70"))
        self.assertTrue(Beneficiary.objects.filter(user=self.user, name="Erion").exists())

    def test_transfer_form_shows_iban_error(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("transfer"), {
            "source": self.acc.pk, "beneficiary_name": "X", "to_iban": "DE89370400440532013001", "amount": "1", "category": "other",
        })
        self.assertContains(response, "check digits")

    def test_statement_csv(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("statement", args=[self.acc.pk]))
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Opening deposit", response.content.decode())

    def test_signup_opens_two_accounts(self):
        response = self.client.post(reverse("signup"), {
            "first_name": "Eva", "last_name": "Kola", "username": "eva", "email": "eva@example.com",
            "password1": "a-Strong-pass-2026", "password2": "a-Strong-pass-2026",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Account.objects.filter(user__username="eva").count(), 2)


class APITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("erin", password="pw-erin-1234")
        self.acc = services.open_account(self.user, "Everyday", opening_balance=Decimal("50.00"))

    def test_api_requires_auth(self):
        self.assertEqual(self.client.get("/api/accounts/").status_code, 403)

    def test_list_accounts_and_make_transfer(self):
        self.client.force_login(self.user)
        data = self.client.get("/api/accounts/").json()
        self.assertEqual(data["results"][0]["iban"], self.acc.iban)
        response = self.client.post("/api/transfers/", {"source": self.acc.pk, "to_iban": "DE89370400440532013000", "amount": "5.00", "beneficiary_name": "X"}, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        response = self.client.post("/api/transfers/", {"source": self.acc.pk, "to_iban": "DE89370400440532013000", "amount": "999.00"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)


class SeedTests(TestCase):
    def test_seed_demo_creates_history_with_consistent_balances(self):
        call_command("seed_demo", verbosity=0)
        for account in Account.objects.filter(user__username="demo"):
            last = account.transactions.order_by("-created_at", "-id").first()
            self.assertEqual(last.balance_after, account.balance)
            self.assertGreaterEqual(account.balance, 0)
