# Brightloop · Subscription Management System

One place to run plans, subscriptions and recurring billing: products with variants, plans,
quotations, subscriptions with a real lifecycle, automatic invoicing with taxes and discounts,
payments, a customer portal and a finance dashboard.

Built for the **Odoo x FLUX Lucknow Hackathon '26** (problem statement: *Subscription Management System*).

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.12+ · Django 6 | Batteries included: ORM + migrations, auth, forms with validation, admin, tests. Odoo-friendly Python. |
| Database | SQLite (default) · PostgreSQL via `DATABASE_URL` | Zero-setup local database; swap to Postgres with one env var. |
| Frontend | Django templates · Bootstrap 5 (vendored) · vanilla JS | Responsive, consistent UI with no build step and no CDN dependency (works offline). |
| API | Django REST Framework (read-only JSON API) | Lets other tools read subscriptions, invoices and KPIs. |
| Charts | Chart.js (vendored) | Dashboard revenue and status charts. |

No static JSON: every screen reads and writes the database.

## Quick start (Windows / macOS / Linux)

```bash
git clone https://github.com/ekansh404/Subscription_Management_System.git
cd Subscription_Management_System

# 1. virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell / cmd)
# source .venv/bin/activate     # macOS / Linux

# 2. dependencies
pip install -r requirements.txt

# 3. database + first administrator
python manage.py migrate
python manage.py createsuperuser   # creates an Administrator (role=admin)

# 4. run
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in. Customers create their own account at `/accounts/signup/`.

> On Windows, if `python` is not found, use `py -3 -m venv .venv` and `py manage.py ...`.

Optional: copy `.env.example` to `.env` to change the secret key, database, email backend or branding.
Password-reset emails are printed to the terminal in development (console email backend).

## Roles

| Role | Who | Can |
| --- | --- | --- |
| Administrator | Brightloop owner | Everything, plus: add staff, manage products/plans/taxes/discounts |
| Staff | Internal team | Customers, quotations, subscriptions, invoices, payments, reports |
| Customer | Self sign-up | Portal: only their own subscriptions and invoices |

Only an administrator can add staff (`Staff` in the sidebar). Customers sign up with an email
(unique) and a password of more than 8 characters containing an uppercase letter, a lowercase
letter and a special character. Forgotten passwords are reset through an emailed link.

## Project layout

```
config/          settings, root URL loop (every app in PROJECT_APPS is mounted at /<app>/)
core/            base layout, theme, navigation registry, role mixins, numbering, date math
accounts/        email-login user model, roles, signup/login/reset, staff management
customers/       customer records (linked to portal accounts)
catalog/         taxes, products + variants (attribute price extras), plans (billing periods)
subscriptions/   quotation templates, subscriptions with lines and lifecycle
billing/         discounts, invoices (auto-generated from subscriptions), billing run
payments/        payment recording, outstanding / overdue tracking
portal/          customer self-service
reports/         finance dashboard with filters and charts
api/             read-only REST API
templates/       one folder per app, shared partials in templates/partials/
static/          app.css (theme), app.js (behaviours), vendored Bootstrap + Chart.js
```

## Demo data

```bash
python manage.py seed_demo --reset     # 25 customers, 60 subscriptions, 6 months of invoices and payments
python manage.py runserver
```

| Login | Password | Sees |
| --- | --- | --- |
| `admin@brightloop.com` | `Admin#12345` | everything, including staff, taxes, attributes, discounts, API |
| `staff@brightloop.com` / `finance@brightloop.com` | `Staff#12345` / `Finance#12345` | day-to-day work and reports |
| `customer1@example.com` … `customer10@example.com` | `Customer#12345` | the customer portal (own data only) |

Your own `createsuperuser` login is kept by `--reset`. Load test (the brief asks for pages under two
seconds with thousands of subscriptions):

```bash
python manage.py seed_demo --reset --subscriptions 3000 --customers 400 --months-back 2   # ~2 minutes
```

Measured locally with that data set (3 000 subscriptions, ~4 800 invoices, ~3 400 payments): dashboard
~230 ms, subscription and invoice lists under 70 ms, receivables ~60 ms.

## Real email (optional)

Emails (password reset links, invoices, overdue reminders) print in the `runserver` terminal by
default, so the app works fully offline. To deliver them for real, copy `.env.example` to `.env`
and fill in the SMTP block (Brevo, Gmail or any SMTP provider), then check it:

```bash
python manage.py sendtestemail you@example.com
```

If the mail server is unreachable the page shows an error message instead of failing; switch
`EMAIL_BACKEND` back to `console` to demo without internet.

## How the brief maps to the product

| Scene in the problem statement | Where |
| --- | --- |
| A new customer signs up (unique email, password policy, reset link, roles, only admin adds staff) | `accounts`, `core/mixins.py` |
| Launching a new plan (product type/prices/notes, variants such as Brand: Odoo +560, plans with period, min quantity, availability, auto-close/close/pause/renew) | `catalog` |
| Turning a quote into a subscription (templates with validity, number, customer, plan, dates, payment terms, lines with taxes, Draft → Quotation → Confirmed → Active → Closed) | `subscriptions` |
| Billing day (invoices generated with customer, lines, taxes, totals; confirm/cancel/send/print; Draft → Confirmed → Paid; nothing billed twice or skipped) | `billing` (+ `manage.py run_billing`) |
| A customer asks for a better price (admin-only discount rules: fixed/%, min purchase/quantity, dates, usage limit, product or subscription scope, applied automatically) | `billing` (discounts) |
| The money comes in (method, amount, date, note; paid vs outstanding vs overdue) | `payments` (payments, receivables) |
| Customers manage their own subscriptions | `portal` |
| The finance lead (active subscriptions, revenue, payments, overdue; filters; summary; fast) | `reports`, `api` |

More detail: [`docs/architecture.md`](docs/architecture.md) (how it is built and why),
[`docs/assumptions.md`](docs/assumptions.md) (decisions where the brief left room) and
[`docs/demo_script.md`](docs/demo_script.md) (the walkthrough used for the video).

## Development

```bash
python manage.py test              # 80+ tests: business rules (services) and views per app
python manage.py check             # Django system checks
python manage.py makemigrations    # after changing models
python manage.py run_billing       # billing day; schedule it daily (cron / Task Scheduler)
```

Continuous integration (GitHub Actions) runs checks, verifies migrations are committed and runs
the tests on every push.

## Roadmap (hackathon build log)

- [x] Stage 1 · Project scaffold, theme, email login, roles, password policy & reset, staff management
- [x] Stage 2 · Customers
- [x] Stage 3 · Catalog: taxes, products with variants, plans
- [x] Stage 4 · Quotation templates & subscriptions with lifecycle
- [x] Stage 5 · Discounts & invoices, billing run
- [x] Stage 6 · Payments, outstanding/overdue tracking, customer portal
- [x] Stage 7 · Finance dashboard, REST API, demo data
- [x] Stage 8 · Polish, documentation, final tests

Next steps we would take: proration when quantities change mid-period, multi-currency, an online
payment gateway with webhooks (e.g. Razorpay) to record payments automatically, automatic dunning
reminders, PostgreSQL in production and a scheduler (Celery beat / cron) for the nightly billing run.

## License

MIT
