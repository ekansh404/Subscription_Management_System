# Demo script (6–8 minutes)

Recorded demo (3 min): https://youtu.be/osQRWMlDtsk

Prepare: `python manage.py seed_demo --reset`, `python manage.py runserver`, two browser windows
(normal + private). Follows the problem statement's month at Brightloop, in order.

## 1. A new customer signs up (45 s)
1. Private window → `/accounts/signup/`. Try password `password1` → rejected (upper, lower, special,
   > 8 chars). Use `Bright#Loop26` with email `newshop@example.com` → lands on their empty portal.
2. Try signing up again with the same email → "An account with this email already exists."
3. Log out → *Forgot password?* → the reset link prints in the `runserver` terminal.
4. Say: admin controls everything, staff day-to-day, customers only their own data, only admin adds staff.

## 2. Launching a new plan (1 min), as `admin@brightloop.com`
1. **Attributes**: Brand with Odoo +560 and Generic.
2. **Products** → *ERP Connector*: variants Odoo (₹3,060) and Generic (₹2,500): Odoo adds 560.
   Show New product: name, type, sales price, cost price, notes, taxes, variant options.
3. **Plans** → *Team Monthly*: price per period, monthly billing, min quantity 5, availability
   window, lifecycle options (auto-close, closable, pausable, renewable) chosen plan by plan.

## 3. Turning a quote into a subscription (1.5 min)
1. **Quotation templates** → *Enterprise bundle (12 months)*: plan, lines, valid 15 days, 12 periods.
2. **Subscriptions** → *From template* → customer *newshop* (from step 1, linked automatically) → Create.
   Show SUB number, dates, payment terms, lines with taxes and live totals (edit a quantity).
3. **Send quotation** → **Confirm** → it becomes **Active**. Point at the status stepper and timeline.
4. Private window (the customer) → refresh portal: the subscription is there.

## 4. A customer asks for a better price (45 s)
1. **Discounts** (admin only) → *10 seats or more*: percentage, min quantity 10, dates, usage limit.
2. On the subscription → Discounts → Apply *10 seats or more*.

## 5. Billing day (1 min)
1. On the subscription → **Invoice now** → invoice with customer details, lines, discount, GST, totals.
2. **Billing run** → Run → shows every invoice that was due. Run it again → "nothing was due": nothing is billed twice.
3. Invoices → **Confirm all drafts**. Open one → **Send by email** (shows in terminal) → **Print**.

## 6. The money comes in (45 s)
1. Invoice → **Register payment** → UPI, half the amount, reference, note → still due.
   Register the rest → **Paid**. Try paying more than due → refused.
2. **Receivables**: outstanding by age, overdue first, one-click reminder.

## 7. The customer manages their own subscription (30 s)
Private window → My subscriptions → **Pause** (allowed by the plan) → My invoices → **Download PDF**.
Try another customer's invoice URL → 404.

## 8. The finance lead (45 s), as `finance@brightloop.com`
**Dashboard**: active subscriptions, MRR/ARR, invoiced, collected, outstanding, overdue, charts.
Filter by plan and dates. **Revenue report** → Export CSV. Mention `/api/` (read-only REST API) and
the 3 000-subscription load test (README).

## Close (15 s)
GitHub: one PR per stage, CI green, 80+ tests on every business rule, docs in `docs/`.
