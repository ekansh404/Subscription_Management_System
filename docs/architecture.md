# Architecture

Brightloop is a server-rendered Django 6 application. One Django app per business area, each with
the same shape:

```
<app>/models.py     data + small model-level helpers (no workflow)
<app>/services.py   business rules: the only code that changes workflow state
<app>/forms.py      input validation (field rules, cross-field clean())
<app>/views.py      thin: permissions, call a service, render
<app>/tests.py      service tests for every rule + view tests for permissions/flows
templates/<app>/    one folder per app, shared pieces in templates/partials/
```

## Apps and dependencies

```
core ─► accounts ─► customers ─► catalog ─► subscriptions ─► billing ─► payments ─► portal
                                                                         └─► reports ─► api
```

Each app only imports from apps to its left. Apps further right add to pages of earlier apps
through reverse relations (for example `subscription.invoices`) rather than imports, so the
dependency graph stays acyclic. Adding an app to `settings.PROJECT_APPS` mounts its URLs at
`/<app>/` and adds its sidebar entries (declared on its `AppConfig.menu`), filtered by role.

## Where the rules live

| Rule | Place |
| --- | --- |
| Password policy (> 8 chars, upper, lower, special) | `accounts/validators.py`, `AUTH_PASSWORD_VALIDATORS` |
| Roles and access (admin / staff / customer) | `core/mixins.py` on every view; DRF permissions in `api/permissions.py` |
| Customer ↔ portal login linking | `customers/services.py` (+ signal on signup) |
| Variant generation and price extras | `catalog/services.generate_variants` |
| Subscription lifecycle, plan options, quotation validity, minimum quantity | `subscriptions/services.py` |
| Invoice generation, taxes, discounts, billing run, cancel/send | `billing/services.py` |
| Payments, overpayment guard, Paid status | `payments/services.record_payment` |
| Finance figures | `reports/services.py` |

Views, the customer portal, the REST API, the `run_billing` command and the `seed_demo`
command all call these functions, so one rule is enforced in one place.

## Guarantees and how they are enforced

**Nothing billed twice.** A partial unique index (`one_invoice_per_subscription_period`) allows one
non-cancelled invoice per `(subscription, period_start)`. `create_invoice` also locks the
subscription row (`select_for_update`) and checks explicitly, then moves `next_invoice_date` past
the period, so a second billing run finds nothing due.

**Nothing skipped.** `bill_subscription` loops while `next_invoice_date <= today` (and not past
expiry), creating every missed period oldest first. Cancelling the latest invoice moves
`next_invoice_date` back so the period is billed again.

**History never changes.** Invoices snapshot the customer (name, email, address, GSTIN) and each
line stores its description, unit price, discount, tax rate and tax names. Editing a customer,
product or tax later does not alter issued invoices.

**Document numbers are unique.** `core/sequences.next_number` increments a named counter inside a
transaction with a row lock (`SUB-00001`, `INV/2026/00001`, `PAY/2026/00001`).

**Customers see only their own data.** Every portal and API queryset is filtered by the signed-in
customer's record; anything else is a 404 (portal) or an empty list (API). Drafts are hidden.

## Performance

* Totals are stored (denormalised) on subscriptions and invoices and kept in sync by the services,
  so lists and reports never recompute line sums.
* Indexes on the columns lists and reports filter by: `status`, `next_invoice_date`, `due_date`,
  `invoice_date`, `(customer, status)`.
* Dashboard figures are SQL aggregates (`Sum`, `Count`, `TruncMonth`), not Python loops.
* Lists use `select_related` / `prefetch_related` and pagination (25 rows).

With 3 000 subscriptions, ~4 800 invoices and ~3 400 payments every page responds well under the
two-second requirement (dashboard ~230 ms, lists < 100 ms on a laptop with SQLite).

## Front end

Django templates, Bootstrap 5 and Chart.js are vendored under `static/vendor`, so the app works
offline with no build step. `static/js/app.js` is plain JavaScript: confirmation prompts,
auto-submitting filters, printing, and the line editor that recalculates totals live and fills in
prices and default taxes when a product is picked.

## Email

Password reset links, invoices and overdue reminders use Django's email API. Development prints
them to the console; set `EMAIL_BACKEND=smtp` and the `EMAIL_*` variables in `.env` to send real
mail through any SMTP provider (Gmail, Brevo, SES...). No code change is needed.
