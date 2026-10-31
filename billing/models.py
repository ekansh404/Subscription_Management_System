"""
Discounts and invoices.

Invoices are generated from subscriptions (``billing.services``), one per
subscription per billing period. Customer details, product names, tax rates
and discounts are copied onto the invoice so it never changes afterwards,
even if a customer, product or tax is edited later.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, ProductVariant
from core.models import TimeStampedModel
from customers.models import Customer
from subscriptions.models import Subscription


class DiscountType(models.TextChoices):
    PERCENT = "percent", "Percentage"
    FIXED = "fixed", "Fixed amount"


class DiscountScope(models.TextChoices):
    SUBSCRIPTION = "subscription", "Whole subscription"
    PRODUCTS = "products", "Specific products"


class Discount(TimeStampedModel):
    """A rule only the admin creates; staff attach it to subscriptions."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, unique=True, help_text="Short reference, e.g. SEATS10.")
    discount_type = models.CharField("type", max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    value = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    scope = models.CharField("applies to", max_length=15, choices=DiscountScope.choices, default=DiscountScope.SUBSCRIPTION)
    products = models.ManyToManyField(Product, blank=True, related_name="discounts")
    min_purchase = models.DecimalField(
        "minimum purchase", max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Untaxed amount of the eligible lines."
    )
    min_quantity = models.DecimalField("minimum quantity", max_digits=10, decimal_places=2, default=Decimal("0"))
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Number of invoices it may apply to. Empty = unlimited.")
    used_count = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)
    subscriptions = models.ManyToManyField(Subscription, blank=True, related_name="discounts")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.value_label})"

    def get_absolute_url(self):
        return reverse("billing:discount_update", args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "The end date must be after the start date."})
        if self.discount_type == DiscountType.PERCENT and self.value and self.value > 100:
            raise ValidationError({"value": "A percentage cannot exceed 100."})

    @property
    def value_label(self) -> str:
        if self.discount_type == DiscountType.PERCENT:
            return f"{self.value.normalize():f}%"
        return f"{self.value:,.2f} off"

    @property
    def uses_left(self) -> int | None:
        return None if self.usage_limit is None else max(self.usage_limit - self.used_count, 0)

    def is_valid_on(self, on: date | None = None) -> bool:
        on = on or timezone.localdate()
        if not self.is_active:
            return False
        if self.start_date and on < self.start_date:
            return False
        if self.end_date and on > self.end_date:
            return False
        return self.uses_left is None or self.uses_left > 0

    @property
    def state(self) -> str:
        today = timezone.localdate()
        if not self.is_active:
            return "inactive"
        if self.uses_left == 0:
            return "exhausted"
        if self.end_date and today > self.end_date:
            return "expired"
        if self.start_date and today < self.start_date:
            return "scheduled"
        return "active"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CONFIRMED = "confirmed", "Confirmed"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"


class Invoice(TimeStampedModel):
    number = models.CharField(max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, null=True, blank=True, related_name="invoices")
    status = models.CharField(max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True)
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    # Snapshot of the customer at invoicing time.
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_address = models.TextField(blank=True)
    customer_tax_id = models.CharField(max_length=30, blank=True)
    amount_untaxed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    sent_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-invoice_date", "-pk"]
        indexes = [models.Index(fields=["status", "due_date"]), models.Index(fields=["customer", "status"])]
        constraints = [
            # Nothing is billed twice: one live invoice per subscription period.
            models.UniqueConstraint(
                fields=["subscription", "period_start"],
                condition=~Q(status="cancelled"),
                name="one_invoice_per_subscription_period",
            )
        ]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self):
        return reverse("billing:invoice_detail", args=[self.pk])

    @property
    def amount_due(self) -> Decimal:
        if self.status == InvoiceStatus.CANCELLED:
            return Decimal("0.00")
        return max(self.amount_total - self.amount_paid, Decimal("0.00"))

    @property
    def is_overdue(self) -> bool:
        return self.status == InvoiceStatus.CONFIRMED and self.amount_due > 0 and self.due_date < timezone.localdate()

    @property
    def payment_state(self) -> str:
        """paid / partial / overdue / due / draft / cancelled, for badges and filters."""
        if self.status in (InvoiceStatus.DRAFT, InvoiceStatus.CANCELLED, InvoiceStatus.PAID):
            return self.status
        if self.is_overdue:
            return "overdue"
        if self.amount_paid > 0:
            return "partial"
        return "due"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    description = models.CharField(max_length=250)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    tax_label = models.CharField(max_length=120, blank=True)
    amount_untaxed = models.DecimalField(max_digits=14, decimal_places=2)
    amount_tax = models.DecimalField(max_digits=14, decimal_places=2)
    amount_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["pk"]

    @property
    def gross_amount(self) -> Decimal:
        return self.amount_untaxed + self.discount_amount


class InvoiceDiscount(models.Model):
    """Which discount rule took how much off an invoice (also the usage record)."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="applied_discounts")
    discount = models.ForeignKey(Discount, on_delete=models.PROTECT, related_name="applications")
    label = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["pk"]
