"""
Quotation templates and subscriptions.

A subscription moves Draft -> Quotation -> Confirmed -> Active -> Closed
(Active <-> Paused when the plan allows it). Every transition goes through
``subscriptions.services`` so the rules live in one place and each change is
written to the subscription's timeline.
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from catalog.models import Plan, ProductVariant, Tax
from core.models import TimeStampedModel
from core.utils import dates
from core.utils.money import round_money
from customers.models import Customer

PAYMENT_TERM_CHOICES = [
    (0, "Immediate payment"),
    (7, "7 days"),
    (15, "15 days"),
    (30, "30 days"),
    (45, "45 days"),
]


class QuotationTemplate(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="templates")
    validity_days = models.PositiveIntegerField(
        "quotation valid for (days)", default=30, help_text="How long a quotation built from this template stays valid."
    )
    duration_periods = models.PositiveIntegerField(
        "contract length (billing periods)",
        null=True,
        blank=True,
        help_text="Sets the expiry date, e.g. 12 on a monthly plan. Leave empty for open-ended.",
    )
    payment_term_days = models.PositiveIntegerField("payment terms", choices=PAYMENT_TERM_CHOICES, default=15)
    notes = models.TextField("terms and notes", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("subscriptions:template_update", args=[self.pk])


class QuotationTemplateLine(models.Model):
    template = models.ForeignKey(QuotationTemplate, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="+", verbose_name="product")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(Decimal("0.01"))])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        ordering = ["pk"]


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    QUOTATION = "quotation", "Quotation"
    CONFIRMED = "confirmed", "Confirmed"
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CLOSED = "closed", "Closed"


EDITABLE_STATUSES = (Status.DRAFT, Status.QUOTATION)
# States that count as a live, billable relationship.
RUNNING_STATUSES = (Status.ACTIVE, Status.PAUSED)


class Subscription(TimeStampedModel):
    number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="subscriptions")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    template = models.ForeignKey(
        QuotationTemplate, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    start_date = models.DateField(db_index=True)
    expiry_date = models.DateField(null=True, blank=True, help_text="Leave empty for an open-ended subscription.")
    quotation_valid_until = models.DateField(null=True, blank=True)
    payment_term_days = models.PositiveIntegerField("payment terms", choices=PAYMENT_TERM_CHOICES, default=15)
    next_invoice_date = models.DateField(null=True, blank=True, db_index=True)
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField("terms and notes", blank=True)
    closed_on = models.DateField(null=True, blank=True)
    close_reason = models.CharField(max_length=200, blank=True)
    # Denormalised totals per billing period, kept in sync by services.recompute_totals().
    amount_untaxed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    mrr = models.DecimalField("monthly recurring revenue", max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_invoice_date"]),
            models.Index(fields=["customer", "status"]),
        ]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self):
        return reverse("subscriptions:subscription_detail", args=[self.pk])

    @property
    def is_editable(self) -> bool:
        return self.status in EDITABLE_STATUSES

    @property
    def billing_period(self) -> str:
        return self.plan.billing_period

    @property
    def pipeline(self) -> list[tuple[str, str, str]]:
        """(code, label, state) for the status stepper: state is done/current/todo."""
        order = [Status.DRAFT, Status.QUOTATION, Status.CONFIRMED, Status.ACTIVE, Status.CLOSED]
        current = Status.ACTIVE if self.status == Status.PAUSED else self.status
        index = order.index(current)
        steps = []
        for position, status in enumerate(order):
            state = "done" if position < index else "current" if position == index else "todo"
            label = "Paused" if status == Status.ACTIVE and self.status == Status.PAUSED else status.label
            steps.append((status.value, label, state))
        return steps


class SubscriptionLine(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="subscription_lines", verbose_name="product")
    description = models.CharField(max_length=250, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"), validators=[MinValueValidator(Decimal("0.01"))])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    taxes = models.ManyToManyField(Tax, blank=True, related_name="+")
    amount_untaxed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_tax = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["pk"]

    def __str__(self) -> str:
        return self.description or str(self.variant)

    def compute_amounts(self) -> None:
        """Requires the line to be saved (taxes are many-to-many)."""
        rate = sum((tax.rate for tax in self.taxes.all()), Decimal("0"))
        self.amount_untaxed = round_money(self.quantity * self.unit_price)
        self.amount_tax = round_money(self.amount_untaxed * rate / Decimal("100"))
        self.amount_total = self.amount_untaxed + self.amount_tax


class SubscriptionEvent(models.Model):
    """Timeline entry: who changed what, and when."""

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12, blank=True)
    message = models.CharField(max_length=300)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return self.message


def monthly_value(subscription: Subscription) -> Decimal:
    return dates.monthly_amount(subscription.amount_untaxed, subscription.plan.billing_period)
