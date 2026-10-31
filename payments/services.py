from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from billing.models import Invoice, InvoiceStatus
from core.sequences import next_number
from subscriptions import services as subscription_services

from .models import Payment


class PaymentError(Exception):
    """Raised when a payment cannot be recorded; the message is shown to the user."""


@transaction.atomic
def record_payment(invoice, amount, *, method, payment_date: date | None = None, reference="", note="", user=None) -> Payment:
    """
    Record a payment against a confirmed invoice. Partial payments are fine;
    paying more than is due is refused. The invoice becomes Paid when its
    amount due reaches zero.
    """
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    amount = Decimal(amount)
    payment_date = payment_date or timezone.localdate()
    if invoice.status == InvoiceStatus.DRAFT:
        raise PaymentError("Confirm the invoice before recording a payment.")
    if invoice.status != InvoiceStatus.CONFIRMED:
        raise PaymentError(f"The invoice is {invoice.get_status_display().lower()}; no payment is expected.")
    if amount <= 0:
        raise PaymentError("The amount must be positive.")
    if amount > invoice.amount_due:
        raise PaymentError(f"The amount exceeds what is due ({invoice.amount_due:,.2f}).")
    if payment_date > timezone.localdate():
        raise PaymentError("The payment date cannot be in the future.")

    payment = Payment.objects.create(
        number=next_number(f"payment-{payment_date.year}", prefix=f"PAY/{payment_date.year}", separator="/"),
        invoice=invoice,
        customer=invoice.customer,
        method=method,
        amount=amount,
        payment_date=payment_date,
        reference=reference,
        note=note,
        recorded_by=user,
    )
    invoice.amount_paid += amount
    if invoice.amount_due == 0:
        invoice.status = InvoiceStatus.PAID
    invoice.save(update_fields=["amount_paid", "status", "updated_at"])
    if invoice.subscription_id:
        state = "fully paid" if invoice.status == InvoiceStatus.PAID else f"{invoice.amount_due:,.2f} still due"
        subscription_services.log(invoice.subscription, f"Payment {payment.number} of {amount:,.2f} on {invoice.number} ({state}).", user=user)
    return payment
