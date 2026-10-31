"""
Billing rules: invoice generation, discounts and the billing run.

* ``create_invoice``   - one invoice for one subscription period, with the
  customer snapshot, product lines, discounts and taxes filled in.
* ``bill_subscription`` - every period that is due, oldest first, so nothing
  is skipped when billing was not run for a while.
* ``run_billing``      - the billing-day job: activate subscriptions that
  start today, bill everything due, close what expired. Safe to run twice:
  ``next_invoice_date`` moves forward with every invoice and a partial
  unique index forbids a second live invoice for the same period.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.utils import timezone

from core.sequences import next_number
from core.utils import dates
from core.utils.money import ZERO, round_money
from subscriptions import services as subscription_services
from subscriptions.models import Status as SubscriptionStatus
from subscriptions.models import Subscription

from .models import Discount, DiscountScope, DiscountType, Invoice, InvoiceDiscount, InvoiceLine, InvoiceStatus


class BillingError(Exception):
    """Raised when an invoice action is not allowed; the message is shown to the user."""


def _today() -> date:
    return timezone.localdate()


# --- discounts ----------------------------------------------------------------


@dataclass
class _Line:
    """Working copy of a subscription line while an invoice is computed."""

    source: object
    gross: Decimal
    discount: Decimal = ZERO
    labels: list = field(default_factory=list)


def _eligible(discount: Discount, lines: list[_Line]) -> list[_Line]:
    if discount.scope == DiscountScope.SUBSCRIPTION:
        return lines
    product_ids = {product.pk for product in discount.products.all()}
    return [line for line in lines if line.source.variant.product_id in product_ids]


def apply_discounts(subscription: Subscription, lines: list[_Line], on: date) -> list[tuple[Discount, Decimal]]:
    """
    Apply every valid discount attached to the subscription to ``lines``
    (in place) and return ``[(discount, amount)]``. Conditions: active,
    within its dates, uses left, minimum quantity and minimum purchase met
    by the eligible lines. Fixed amounts are spread over the eligible lines
    in proportion to their value and never exceed what is left to discount.
    """
    applied = []
    for discount in subscription.discounts.prefetch_related("products").order_by("pk"):
        if not discount.is_valid_on(on):
            continue
        eligible = _eligible(discount, lines)
        if not eligible:
            continue
        quantity = sum(line.source.quantity for line in eligible)
        base = sum(line.gross - line.discount for line in eligible)
        if quantity < discount.min_quantity or base < discount.min_purchase or base <= 0:
            continue
        if discount.discount_type == DiscountType.PERCENT:
            total = round_money(base * discount.value / Decimal("100"))
        else:
            total = min(round_money(discount.value), base)
        remaining = total
        for index, line in enumerate(eligible):
            available = line.gross - line.discount
            share = remaining if index == len(eligible) - 1 else round_money(total * available / base)
            share = min(share, available, remaining)
            line.discount += share
            remaining -= share
        applied.append((discount, total - remaining))
    return [(discount, amount) for discount, amount in applied if amount > 0]


# --- invoices -----------------------------------------------------------------


def _invoice_number(on: date) -> str:
    return next_number(f"invoice-{on.year}", prefix=f"INV/{on.year}", separator="/")


@transaction.atomic
def create_invoice(subscription: Subscription, period_start: date | None = None) -> Invoice:
    """Invoice one billing period of ``subscription`` (default: its next due period)."""
    subscription = Subscription.objects.select_for_update().select_related("customer", "plan").get(pk=subscription.pk)
    period_start = period_start or subscription.next_invoice_date
    if period_start is None:
        raise BillingError(f"{subscription.number} has no billing period due.")
    if subscription.status not in (SubscriptionStatus.ACTIVE,):
        raise BillingError(f"{subscription.number} is {subscription.get_status_display().lower()}; only active subscriptions are billed.")
    if subscription.invoices.exclude(status=InvoiceStatus.CANCELLED).filter(period_start=period_start).exists():
        raise BillingError(f"{subscription.number} is already invoiced for the period starting {period_start:%d %b %Y}.")

    period_end = dates.period_end(period_start, subscription.plan.billing_period)
    if subscription.expiry_date:
        period_end = min(period_end, subscription.expiry_date)
    customer = subscription.customer
    invoice = Invoice(
        number=_invoice_number(period_start),
        customer=customer,
        subscription=subscription,
        invoice_date=period_start,
        due_date=period_start + timedelta(days=subscription.payment_term_days),
        period_start=period_start,
        period_end=period_end,
        customer_name=customer.display_name,
        customer_email=customer.email,
        customer_address="\n".join(customer.address_lines),
        customer_tax_id=customer.tax_id,
        notes=subscription.notes,
    )
    try:
        with transaction.atomic():
            invoice.save()
    except IntegrityError as error:  # a concurrent run got there first
        raise BillingError(f"{subscription.number} is already invoiced for this period.") from error

    work = [
        _Line(source=line, gross=round_money(line.quantity * line.unit_price))
        for line in subscription.lines.select_related("variant__product").prefetch_related("taxes")
    ]
    applied = apply_discounts(subscription, work, period_start)

    untaxed = discount_total = tax_total = ZERO
    for item in work:
        line = item.source
        taxes = list(line.taxes.all())
        rate = sum((tax.rate for tax in taxes), ZERO)
        net = item.gross - item.discount
        tax = round_money(net * rate / Decimal("100"))
        InvoiceLine.objects.create(
            invoice=invoice,
            variant=line.variant,
            description=f"{line} ({period_start:%d %b} – {period_end:%d %b %Y})",
            quantity=line.quantity,
            unit_price=line.unit_price,
            discount_amount=item.discount,
            tax_rate=rate,
            tax_label=", ".join(f"{tax.name} {tax.rate.normalize():f}%" for tax in taxes),
            amount_untaxed=net,
            amount_tax=tax,
            amount_total=net + tax,
        )
        untaxed += net
        discount_total += item.discount
        tax_total += tax

    for discount, amount in applied:
        InvoiceDiscount.objects.create(invoice=invoice, discount=discount, label=str(discount), amount=amount)
        Discount.objects.filter(pk=discount.pk).update(used_count=F("used_count") + 1)

    invoice.amount_untaxed = untaxed
    invoice.amount_discount = discount_total
    invoice.amount_tax = tax_total
    invoice.amount_total = untaxed + tax_total
    invoice.save(update_fields=["amount_untaxed", "amount_discount", "amount_tax", "amount_total", "updated_at"])

    subscription.next_invoice_date = period_end + timedelta(days=1)
    subscription.save(update_fields=["next_invoice_date", "updated_at"])
    subscription_services.log(subscription, f"Invoice {invoice.number} created for {period_start:%d %b} – {period_end:%d %b %Y}.")
    return invoice


def due_periods_remaining(subscription: Subscription, today: date) -> bool:
    next_date = subscription.next_invoice_date
    if subscription.status != SubscriptionStatus.ACTIVE or next_date is None or next_date > today:
        return False
    return subscription.expiry_date is None or next_date <= subscription.expiry_date


def bill_subscription(subscription: Subscription, today: date | None = None) -> list[Invoice]:
    """Create every invoice that is due for ``subscription`` up to ``today``."""
    today = today or _today()
    invoices = []
    subscription.refresh_from_db()
    while due_periods_remaining(subscription, today):
        invoices.append(create_invoice(subscription))
        subscription.refresh_from_db()
    return invoices


@dataclass
class BillingRunResult:
    run_date: date
    activated: int = 0
    invoices: list = field(default_factory=list)
    closed: int = 0
    errors: list = field(default_factory=list)

    @property
    def invoiced_amount(self) -> Decimal:
        return sum((invoice.amount_total for invoice in self.invoices), ZERO)


def due_subscriptions(today: date):
    return Subscription.objects.filter(status=SubscriptionStatus.ACTIVE, next_invoice_date__lte=today).select_related("plan")


def run_billing(today: date | None = None, *, auto_confirm: bool = False) -> BillingRunResult:
    """Billing day. Idempotent: running it again the same day creates nothing."""
    today = today or _today()
    result = BillingRunResult(run_date=today)
    result.activated = subscription_services.activate_due(today)
    for subscription in due_subscriptions(today).iterator():
        try:
            invoices = bill_subscription(subscription, today)
        except BillingError as error:
            result.errors.append(str(error))
            continue
        if auto_confirm:
            for invoice in invoices:
                confirm_invoice(invoice)
        result.invoices.extend(invoices)
    result.closed = subscription_services.close_expired(today)
    return result


# --- queries ---------------------------------------------------------------------


def filter_invoices(queryset, state, today=None):
    """Apply a payment-state filter (shared by the staff list, portal and reports)."""
    today = today or timezone.localdate()
    open_q = Q(status=InvoiceStatus.CONFIRMED)
    if state in ("draft", "paid", "cancelled"):
        return queryset.filter(status=state)
    if state == "outstanding":
        return queryset.filter(open_q)
    if state == "overdue":
        return queryset.filter(open_q, due_date__lt=today)
    if state == "partial":
        return queryset.filter(open_q, amount_paid__gt=0, due_date__gte=today)
    if state == "due":
        return queryset.filter(open_q, amount_paid=0, due_date__gte=today)
    return queryset


# --- invoice workflow ---------------------------------------------------------


def confirm_invoice(invoice: Invoice) -> Invoice:
    if invoice.status != InvoiceStatus.DRAFT:
        raise BillingError("Only draft invoices can be confirmed.")
    invoice.status = InvoiceStatus.CONFIRMED
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


@transaction.atomic
def cancel_invoice(invoice: Invoice) -> Invoice:
    """
    Cancel a draft or confirmed invoice without payments. Discount uses are
    given back, and if it was the subscription's latest period the period is
    re-opened so it is billed again (nothing skipped).
    """
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.CONFIRMED):
        raise BillingError(f"A {invoice.get_status_display().lower()} invoice cannot be cancelled.")
    if invoice.amount_paid > 0:
        raise BillingError("This invoice has payments recorded; it cannot be cancelled.")
    invoice.status = InvoiceStatus.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])
    for applied in invoice.applied_discounts.all():
        Discount.objects.filter(pk=applied.discount_id, used_count__gt=0).update(used_count=F("used_count") - 1)
    subscription = invoice.subscription
    if subscription and invoice.period_end and subscription.next_invoice_date == invoice.period_end + timedelta(days=1):
        subscription.next_invoice_date = invoice.period_start
        subscription.save(update_fields=["next_invoice_date", "updated_at"])
        subscription_services.log(subscription, f"Invoice {invoice.number} cancelled; the period will be billed again.")
    return invoice


def send_invoice(invoice: Invoice, request=None) -> Invoice:
    """Email the invoice to the customer (confirming it first if it is a draft)."""
    if invoice.status == InvoiceStatus.CANCELLED:
        raise BillingError("A cancelled invoice cannot be sent.")
    if invoice.status == InvoiceStatus.DRAFT:
        confirm_invoice(invoice)
    link = request.build_absolute_uri(invoice.get_absolute_url()) if request else ""
    body = render_to_string("billing/invoice_email.txt", {"invoice": invoice, "link": link, "app_name": settings.APP_NAME})
    send_mail(
        f"{settings.APP_NAME} invoice {invoice.number}",
        body,
        settings.DEFAULT_FROM_EMAIL,
        [invoice.customer_email],
    )
    invoice.sent_at = timezone.now()
    invoice.save(update_fields=["sent_at", "updated_at"])
    return invoice
