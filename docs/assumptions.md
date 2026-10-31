# Assumptions and decisions

Where the problem statement left room, this is what we decided and why.

## Accounts and roles
* "More than eight characters" means at least 9. Emails are case-insensitive and unique.
* Self-signup always creates a **customer**. Staff and admins are created only by an admin.
* Admins can do everything staff can do.
* A customer login is linked to a customer record by email. If staff created the customer first,
  the signup attaches to that record (no duplicates).

## Catalog
* Product **type** is service/software, add-on or physical goods.
* Variants are every combination of the chosen attribute values. Each value's price extra is
  added to the sales price (Brand: Odoo → +560). Removing a value archives variants rather than
  deleting them, so existing subscription lines keep working.
* A **plan** has a price per billing period and an optional default product. Lines added from a
  plan use the plan price and minimum quantity; other lines use the variant price.
* **Minimum quantity** is checked against the quantity of the plan's product (or all lines when
  the plan has no default product) when the subscription is confirmed.
* **Availability dates** decide whether a subscription may start on that plan on its start date.

## Subscriptions
* Draft → Quotation (sent, valid for the template's days, 30 by default) → Confirmed (accepted)
  → Active (start date reached; immediately if it already has) → Closed. Paused is a sub-state of
  Active.
* A quotation past its validity date cannot be confirmed; sending it again renews validity.
* Only drafts and quotations can be edited; after confirmation the lines are the contract.
* Pause, early close and renew follow the plan's options, for staff and customers alike.
  Plans with auto-close on are closed by the billing run the day after their expiry date, even
  when they cannot be closed early.
* Renew extends the expiry date by the original contract length (or one billing period for
  open-ended subscriptions). Renewing a closed subscription reopens it and billing resumes.
* Resuming after a pause bills from the resume date; paused periods are not invoiced.

## Billing
* Billing in advance: an invoice covers `[period_start, period_end]` and is dated on the period
  start. The due date is that date plus the payment terms.
* The billing run creates **draft** invoices (staff review, then "Confirm all drafts"), or confirms
  them immediately when the option is ticked. Billing stops at the expiry date; the last period is
  shortened to it (no proration of the price).
* Taxes are per line and are the sum of the line's tax rates, applied after discounts.
* Discounts: one use = one invoice. Conditions (minimum quantity and minimum purchase) are
  evaluated on the eligible lines of each invoice. Several discounts can stack; fixed amounts
  never take a line below zero. Cancelling an invoice gives the use back.
* Cancelling is allowed for draft or confirmed invoices without payments.

## Payments
* Payments are recorded by staff against confirmed invoices. Partial payments are allowed;
  overpayments and future dates are refused. An invoice becomes **Paid** when nothing is due.
* **Overdue** = confirmed, amount due > 0, due date in the past. **Outstanding** = all confirmed
  invoices with an amount due.
* Online payment (e.g. Razorpay with webhooks) is out of scope for the hackathon. The service
  `record_payment` is the single entry point a webhook would call.

## Reports
* Revenue invoiced counts confirmed and paid invoices dated in the period (tax included).
  Collected counts payments dated in the period. MRR is the untaxed monthly value of active
  subscriptions (yearly / 12, weekly × 52 / 12, daily × 30).
* Currency is INR (₹), configurable with `CURRENCY_SYMBOL` / `CURRENCY_CODE`.
