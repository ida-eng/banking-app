# Arka: online banking demo (Django)

A small online-banking app built with **Django 5** and **Django REST Framework**: accounts with real-format IBANs, SEPA and instant transfers, spending insights, statements and a REST API.

**Live demo:** https://arka-bank.onrender.com · click **“Try the demo account”** on the login page.

> Portfolio project. The bank is fictional and no real money moves.

## Features

- **Sign up / log in**, plus a one-click shared demo account with 5 months of realistic activity
- **Accounts:** every customer gets an Everyday and a Savings account with checksum-valid Albanian IBANs
- **Transfers**
  - to any SEPA IBAN, validated with the ISO 13616 mod-97 checksum and per-country length rules (server-side, and live in the browser as you type)
  - transfers to another Arka IBAN are credited instantly in the same database transaction
  - balance checks, two-decimal amounts, a per-transfer limit and saved recipients
- **Consistency:** every balance change runs inside `transaction.atomic()` with `select_for_update()`, rows locked in a fixed order to avoid deadlocks, and each transaction stores the running `balance_after`
- **Insights:** total balance, money in and out this month, a 6-month in/out chart and spending by category (Chart.js)
- **Transactions:** search, filter by type, category and date range, pagination
- **Statements:** download the filtered list as CSV
- **REST API** (`/api/`): read accounts and transactions, `POST /api/transfers/`; session or basic auth, browsable in the browser
- **Admin** for accounts, transactions and recipients
- **Tests** for IBAN validation, transfer rules, permissions, views, the API and seed data

## Tech

Python 3.12 · Django 5.2 · Django REST Framework · SQLite (or Postgres via `DATABASE_URL`) · WhiteNoise · Gunicorn · Chart.js · deployed on Render

## Project layout

```
arka/                      settings and root URLs
banking/iban.py            IBAN normalise / validate / generate (pure Python)
banking/services.py        open_account, deposit, withdraw, transfer, demo history
banking/models.py          Account, Transaction, Beneficiary
banking/views.py           dashboard, account, statement, transfer, recipients, auth
banking/api.py             DRF serializers and viewsets
banking/tests.py           test suite
banking/management/commands/seed_demo.py
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # creates the demo user
python manage.py runserver
python manage.py test             # run the tests
```

## API examples

```bash
curl -u demo:demo-password-123 https://<your-app>.onrender.com/api/accounts/
curl -u demo:demo-password-123 -H "Content-Type: application/json" \
  -d '{"source": 1, "to_iban": "DE89 3704 0044 0532 0130 00", "amount": "12.50", "beneficiary_name": "Studio Mila"}' \
  https://<your-app>.onrender.com/api/transfers/
```

## Deploy

`render.yaml` describes the service. On Render, choose **New → Blueprint**, pick this repository and apply. The build runs migrations and seeds the demo account. On the free plan the SQLite file resets on each deploy or restart, which is fine for a demo; set `DATABASE_URL` to use Postgres instead.

Built by [Aida Topalli](https://ida-eng.github.io/portfolio/).
