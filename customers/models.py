"""
Customers: the companies and people Brightloop bills.

A customer record is the billing identity (name, address, tax id). It can be
linked to a portal login (``accounts.User`` with the customer role) so the
customer sees their own subscriptions and invoices. The link is made
automatically when the emails match (see ``customers.services``).
"""

from django.conf import settings
from django.db import models
from django.urls import reverse

from core.models import TimeStampedModel


class Customer(TimeStampedModel):
    name = models.CharField(max_length=150, help_text="Person or company name shown on invoices.")
    company = models.CharField(max_length=150, blank=True)
    email = models.EmailField(
        unique=True,
        error_messages={"unique": "A customer with this email already exists."},
    )
    phone = models.CharField(max_length=30, blank=True)
    street = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True, default="India")
    tax_id = models.CharField("GSTIN / tax ID", max_length=30, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_profile",
        help_text="Portal login linked to this customer.",
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("customers:detail", args=[self.pk])

    @property
    def display_name(self) -> str:
        if self.company and self.company != self.name:
            return f"{self.name} ({self.company})"
        return self.name

    @property
    def address_lines(self) -> list[str]:
        """Postal address as printable lines (used on invoices)."""
        city_line = " ".join(part for part in (self.city, self.postal_code) if part)
        return [line for line in (self.street, city_line, self.state, self.country) if line]

    @property
    def has_portal_access(self) -> bool:
        return self.user_id is not None
