"""
Catalog: what Brightloop sells and how often it bills.

* ``Tax``              - rules the admin sets (e.g. GST 18%); applied per line.
* ``ProductAttribute`` - a dimension such as *Brand*, with ``AttributeValue``s
  that may add to the price (choosing *Odoo* adds 560).
* ``Product``          - name, type, sales price, cost price, notes, default taxes.
* ``ProductVariant``   - one sellable combination of attribute values, generated
  by ``catalog.services.generate_variants``. Every product has at least one.
* ``Plan``             - recurring price and billing period, minimum quantity,
  availability window and the lifecycle options the admin allows.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from core.models import TimeStampedModel
from core.utils import dates


class Tax(TimeStampedModel):
    name = models.CharField(max_length=60, unique=True)
    rate = models.DecimalField(
        "rate (%)",
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "taxes"

    def __str__(self) -> str:
        return f"{self.name} ({self.rate.normalize():f}%)"


class ProductAttribute(TimeStampedModel):
    name = models.CharField(max_length=60, unique=True, help_text="For example Brand, Edition or Region.")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AttributeValue(models.Model):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="values")
    name = models.CharField(max_length=60)
    price_extra = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), help_text="Added to the product price when chosen."
    )
    sequence = models.PositiveIntegerField(default=10)

    class Meta:
        ordering = ["attribute__name", "sequence", "name"]
        constraints = [models.UniqueConstraint(fields=["attribute", "name"], name="unique_attribute_value")]

    def __str__(self) -> str:
        extra = f" (+{self.price_extra:,.2f})" if self.price_extra else ""
        return f"{self.attribute.name}: {self.name}{extra}"


class ProductType(models.TextChoices):
    SERVICE = "service", "Service / software"
    ADDON = "addon", "Add-on"
    GOODS = "goods", "Physical goods"


class Product(TimeStampedModel):
    name = models.CharField(max_length=150)
    product_type = models.CharField("type", max_length=20, choices=ProductType.choices, default=ProductType.SERVICE)
    sales_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0"))]
    )
    notes = models.TextField(blank=True)
    taxes = models.ManyToManyField(Tax, blank=True, related_name="products", help_text="Default taxes on sales lines.")
    attribute_values = models.ManyToManyField(
        AttributeValue,
        blank=True,
        related_name="products",
        help_text="Variants are generated for every combination of the values chosen here.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:product_detail", args=[self.pk])

    @property
    def margin(self) -> Decimal:
        return self.sales_price - self.cost_price


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    values = models.ManyToManyField(AttributeValue, blank=True, related_name="variants")
    # Sorted value ids ("3-7"); empty for the default variant of a product without attributes.
    combination_key = models.CharField(max_length=200, blank=True)
    name = models.CharField(max_length=250)
    price_extra = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product__name", "name"]
        constraints = [models.UniqueConstraint(fields=["product", "combination_key"], name="unique_variant_combination")]

    def __str__(self) -> str:
        return self.name

    @property
    def price(self) -> Decimal:
        return self.product.sales_price + self.price_extra

    @property
    def tax_rate(self) -> Decimal:
        return sum((tax.rate for tax in self.product.taxes.all()), Decimal("0"))


class BillingPeriod(models.TextChoices):
    DAILY = dates.DAILY, "Daily"
    WEEKLY = dates.WEEKLY, "Weekly"
    MONTHLY = dates.MONTHLY, "Monthly"
    YEARLY = dates.YEARLY, "Yearly"


class Plan(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    product = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="plans",
        help_text="Default product line added when a subscription uses this plan.",
    )
    price = models.DecimalField(
        "price per period", max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    billing_period = models.CharField(max_length=10, choices=BillingPeriod.choices, default=BillingPeriod.MONTHLY)
    min_quantity = models.PositiveIntegerField("minimum quantity", default=1, validators=[MinValueValidator(1)])
    start_date = models.DateField("available from", null=True, blank=True)
    end_date = models.DateField("available until", null=True, blank=True)
    auto_close = models.BooleanField(
        "close automatically at expiry", default=True, help_text="Subscriptions close on their own when they end."
    )
    closable = models.BooleanField("can be closed early", default=True)
    pausable = models.BooleanField("can be paused", default=False)
    renewable = models.BooleanField("can be renewed", default=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_billing_period_display()})"

    def get_absolute_url(self):
        return reverse("catalog:plan_detail", args=[self.pk])

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "The end date must be after the start date."})

    def is_available(self, on: date | None = None) -> bool:
        """Can a new subscription start on this plan on ``on`` (default today)?"""
        on = on or date.today()
        if not self.is_active:
            return False
        if self.start_date and on < self.start_date:
            return False
        if self.end_date and on > self.end_date:
            return False
        return True

    @property
    def monthly_price(self) -> Decimal:
        return dates.monthly_amount(self.price, self.billing_period)

    @property
    def lifecycle_options(self) -> list[str]:
        options = []
        if self.auto_close:
            options.append("Auto-close")
        if self.closable:
            options.append("Closable")
        if self.pausable:
            options.append("Pausable")
        if self.renewable:
            options.append("Renewable")
        return options
