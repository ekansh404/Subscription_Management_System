"""
Payments received against invoices.

Each payment records its method, amount, date and a note against exactly one
invoice. ``payments.services.record_payment`` keeps the invoice's paid amount
and status in step (Confirmed -> Paid once nothing is left to pay).
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from billing.models import Invoice
from core.models import TimeStampedModel
from customers.models import Customer


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    UPI = "upi", "UPI"
    CARD = "card", "Card"
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"


class Payment(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_date = models.DateField(db_index=True)
    reference = models.CharField(max_length=80, blank=True, help_text="Bank / UPI transaction id, cheque number...")
    note = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-payment_date", "-pk"]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self):
        return reverse("payments:payment_receipt", args=[self.pk])
