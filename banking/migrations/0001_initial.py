import decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60)),
                ("kind", models.CharField(choices=[("current", "Current account"), ("savings", "Savings account")], default="current", max_length=10)),
                ("iban", models.CharField(max_length=34, unique=True)),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("balance", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="accounts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["kind", "created_at"]},
        ),
        migrations.CreateModel(
            name="Beneficiary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=70)),
                ("iban", models.CharField(max_length=34)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="beneficiaries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("credit", "Money in"), ("debit", "Money out")], max_length=6)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(decimal.Decimal("0.01"))])),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=12)),
                ("category", models.CharField(choices=[("salary", "Salary"), ("transfer", "Transfer"), ("groceries", "Groceries"), ("rent", "Rent & bills"), ("dining", "Dining"), ("transport", "Transport"), ("shopping", "Shopping"), ("entertainment", "Entertainment"), ("health", "Health"), ("other", "Other")], default="other", max_length=20)),
                ("description", models.CharField(max_length=140)),
                ("counterparty_name", models.CharField(blank=True, max_length=70)),
                ("counterparty_iban", models.CharField(blank=True, max_length=34)),
                ("reference", models.CharField(blank=True, max_length=140)),
                ("transfer_id", models.UUIDField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transactions", to="banking.account")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="beneficiary",
            constraint=models.UniqueConstraint(fields=("user", "iban"), name="unique_beneficiary_per_user"),
        ),
    ]
