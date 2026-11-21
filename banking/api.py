from decimal import Decimal

from rest_framework import serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from . import iban as ibanlib
from . import services
from .models import Account, Transaction


class AccountSerializer(serializers.ModelSerializer):
    iban_display = serializers.CharField(read_only=True)

    class Meta:
        model = Account
        fields = ["id", "name", "kind", "iban", "iban_display", "currency", "balance", "created_at"]


class TransactionSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "account", "kind", "amount", "balance_after", "category", "description",
            "counterparty_name", "counterparty_iban", "reference", "transfer_id", "created_at",
        ]


class TransferSerializer(serializers.Serializer):
    source = serializers.IntegerField(help_text="ID of one of your accounts")
    to_iban = serializers.CharField(max_length=42)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    beneficiary_name = serializers.CharField(max_length=70, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=140, required=False, allow_blank=True, default="")

    def validate_to_iban(self, value):
        try:
            return ibanlib.validate(value)
        except ibanlib.IBANError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """Your bank accounts."""

    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(user=self.request.user)


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Your transactions, newest first. Filter with ?account=<id>&kind=debit&category=groceries"""

    serializer_class = TransactionSerializer

    def get_queryset(self):
        qs = Transaction.objects.filter(account__user=self.request.user)
        for field in ("account", "kind", "category"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs


class TransferView(APIView):
    """POST a transfer: {"source": 1, "to_iban": "DE89...", "amount": "25.00", "beneficiary_name": "...", "reference": "..."}"""

    def post(self, request):
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        source = Account.objects.filter(pk=d["source"], user=request.user).first()
        if source is None:
            return Response({"source": ["Account not found."]}, status=status.HTTP_404_NOT_FOUND)
        try:
            result = services.transfer(
                source=source, to_iban=d["to_iban"], amount=d["amount"],
                beneficiary_name=d["beneficiary_name"], reference=d["reference"],
            )
        except services.TransferError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"internal": result.internal, "transaction": TransactionSerializer(result.debit).data},
            status=status.HTTP_201_CREATED,
        )
