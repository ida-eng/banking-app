from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from . import iban as ibanlib
from .models import Account, Beneficiary, Transaction


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")


class IBANField(forms.CharField):
    def clean(self, value):
        value = super().clean(value)
        if not value and not self.required:
            return ""
        try:
            return ibanlib.validate(value)
        except ibanlib.IBANError as exc:
            raise forms.ValidationError(str(exc)) from exc


class TransferForm(forms.Form):
    source = forms.ModelChoiceField(queryset=Account.objects.none(), label="From", empty_label=None)
    beneficiary = forms.ModelChoiceField(queryset=Beneficiary.objects.none(), required=False, label="Saved recipient", empty_label="New recipient")
    beneficiary_name = forms.CharField(max_length=70, required=False, label="Recipient name")
    to_iban = IBANField(max_length=42, required=False, label="Recipient IBAN")
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2, label="Amount (EUR)")
    reference = forms.CharField(max_length=140, required=False, label="Reference")
    category = forms.ChoiceField(choices=Transaction.Category.choices, initial=Transaction.Category.TRANSFER)
    save_beneficiary = forms.BooleanField(required=False, label="Save this recipient")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["source"].queryset = Account.objects.filter(user=user)
        self.fields["beneficiary"].queryset = Beneficiary.objects.filter(user=user)
        self.fields["source"].label_from_instance = lambda a: f"{a.name} · €{a.balance:,.2f}"

    def clean(self):
        data = super().clean()
        saved = data.get("beneficiary")
        if saved:
            data["to_iban"] = saved.iban
            data["beneficiary_name"] = data.get("beneficiary_name") or saved.name
        elif not data.get("to_iban") and "to_iban" not in self.errors:
            self.add_error("to_iban", "Enter the recipient's IBAN or choose a saved recipient.")
        if not saved and not data.get("beneficiary_name"):
            own = Account.objects.filter(user=self.user, iban=data.get("to_iban")).exists()
            if not own:
                self.add_error("beneficiary_name", "Enter the recipient's name.")
        return data


class BeneficiaryForm(forms.ModelForm):
    iban = IBANField(max_length=42, label="IBAN")

    class Meta:
        model = Beneficiary
        fields = ("name", "iban")


class TransactionFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search")
    kind = forms.ChoiceField(required=False, choices=[("", "All")] + list(Transaction.Kind.choices))
    category = forms.ChoiceField(required=False, choices=[("", "All categories")] + list(Transaction.Category.choices))
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="From")
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="To")
