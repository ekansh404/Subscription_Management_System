"""
Finance figures, computed with SQL aggregates (no Python loops over rows) so
the dashboard stays fast with thousands of subscriptions and invoices.

Definitions used everywhere:
* Revenue invoiced   - total of confirmed + paid invoices dated in the period
* Collected          - payments received in the period
* Outstanding        - amount still due on confirmed invoices (any date)
* Overdue            - outstanding amount whose due date has passed
* MRR                - monthly value of active subscriptions (untaxed)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from billing.models import Invoice, InvoiceStatus
from core.utils.dates import add_months
from payments.models import Payment
from subscriptions.models import Status, Subscription

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))
BILLED = (InvoiceStatus.CONFIRMED, InvoiceStatus.PAID)


@dataclass
class ReportFilters:
    date_from: date
    date_to: date
    plan_id: int | None = None
    customer_id: int | None = None

    @classmethod
    def default(cls):
        today = timezone.localdate()
        return cls(date_from=add_months(today.replace(day=1), -5), date_to=today)


def _invoices(filters: ReportFilters):
    queryset = Invoice.objects.all()
    if filters.plan_id:
        queryset = queryset.filter(subscription__plan_id=filters.plan_id)
    if filters.customer_id:
        queryset = queryset.filter(customer_id=filters.customer_id)
    return queryset


def _payments(filters: ReportFilters):
    queryset = Payment.objects.filter(payment_date__range=(filters.date_from, filters.date_to))
    if filters.plan_id:
        queryset = queryset.filter(invoice__subscription__plan_id=filters.plan_id)
    if filters.customer_id:
        queryset = queryset.filter(customer_id=filters.customer_id)
    return queryset


def _subscriptions(filters: ReportFilters):
    queryset = Subscription.objects.all()
    if filters.plan_id:
        queryset = queryset.filter(plan_id=filters.plan_id)
    if filters.customer_id:
        queryset = queryset.filter(customer_id=filters.customer_id)
    return queryset


def kpis(filters: ReportFilters) -> dict:
    today = timezone.localdate()
    subscriptions = _subscriptions(filters).aggregate(
        active=Count("pk", filter=Q(status=Status.ACTIVE)),
        paused=Count("pk", filter=Q(status=Status.PAUSED)),
        quotations=Count("pk", filter=Q(status__in=[Status.DRAFT, Status.QUOTATION])),
        mrr=Coalesce(Sum("mrr", filter=Q(status=Status.ACTIVE)), ZERO),
        new=Count("pk", filter=Q(start_date__range=(filters.date_from, filters.date_to)) & ~Q(status__in=[Status.DRAFT, Status.QUOTATION])),
        churned=Count("pk", filter=Q(status=Status.CLOSED, closed_on__range=(filters.date_from, filters.date_to))),
    )
    invoices = _invoices(filters)
    billed = invoices.filter(status__in=BILLED, invoice_date__range=(filters.date_from, filters.date_to)).aggregate(
        invoiced=Coalesce(Sum("amount_total"), ZERO), count=Count("pk"), tax=Coalesce(Sum("amount_tax"), ZERO),
        discount=Coalesce(Sum("amount_discount"), ZERO),
    )
    open_invoices = invoices.filter(status=InvoiceStatus.CONFIRMED).annotate(due=F("amount_total") - F("amount_paid"))
    outstanding = open_invoices.aggregate(amount=Coalesce(Sum("due"), ZERO), count=Count("pk"))
    overdue = open_invoices.filter(due_date__lt=today).aggregate(amount=Coalesce(Sum("due"), ZERO), count=Count("pk"))
    collected = _payments(filters).aggregate(amount=Coalesce(Sum("amount"), ZERO), count=Count("pk"))
    collection_rate = (collected["amount"] / billed["invoiced"] * 100) if billed["invoiced"] else None
    return {
        "subscriptions": subscriptions,
        "arr": subscriptions["mrr"] * 12,
        "billed": billed,
        "outstanding": outstanding,
        "overdue": overdue,
        "collected": collected,
        "collection_rate": collection_rate,
    }


def monthly_series(filters: ReportFilters) -> list[dict]:
    """Invoiced, collected, discounts and taxes per month in the range (months with nothing included)."""
    invoiced = {
        row["month"]: row
        for row in _invoices(filters)
        .filter(status__in=BILLED, invoice_date__range=(filters.date_from, filters.date_to))
        .annotate(month=TruncMonth("invoice_date"))
        .values("month")
        .annotate(
            invoiced=Sum("amount_total"), untaxed=Sum("amount_untaxed"), tax=Sum("amount_tax"),
            discount=Sum("amount_discount"), count=Count("pk"),
        )
        .order_by()
    }
    collected = {
        row["month"]: row["amount"]
        for row in _payments(filters).annotate(month=TruncMonth("payment_date")).values("month").annotate(amount=Sum("amount")).order_by()
    }
    rows = []
    month = filters.date_from.replace(day=1)
    while month <= filters.date_to:
        data = invoiced.get(month, {})
        rows.append(
            {
                "month": month,
                "invoiced": data.get("invoiced") or Decimal("0"),
                "untaxed": data.get("untaxed") or Decimal("0"),
                "tax": data.get("tax") or Decimal("0"),
                "discount": data.get("discount") or Decimal("0"),
                "count": data.get("count") or 0,
                "collected": collected.get(month) or Decimal("0"),
            }
        )
        month = add_months(month, 1)
    return rows


def status_breakdown(filters: ReportFilters) -> list[tuple[str, int]]:
    counts = dict(_subscriptions(filters).values_list("status").annotate(n=Count("pk")).order_by())
    return [(label, counts.get(code, 0)) for code, label in Status.choices]


def mrr_by_plan(filters: ReportFilters, limit: int = 8):
    return (
        _subscriptions(filters)
        .filter(status=Status.ACTIVE)
        .values("plan__name")
        .annotate(mrr=Sum("mrr"), count=Count("pk"))
        .order_by("-mrr")[:limit]
    )


def top_overdue(filters: ReportFilters, limit: int = 8):
    return (
        _invoices(filters)
        .filter(status=InvoiceStatus.CONFIRMED, due_date__lt=timezone.localdate())
        .annotate(due=F("amount_total") - F("amount_paid"))
        .select_related("customer")
        .order_by("due_date")[:limit]
    )


def revenue_by(filters: ReportFilters, group: str):
    field = {"plan": "subscription__plan__name", "customer": "customer__name"}[group]
    return (
        _invoices(filters)
        .filter(status__in=BILLED, invoice_date__range=(filters.date_from, filters.date_to))
        .values(field)
        .annotate(invoiced=Sum("amount_total"), paid=Sum("amount_paid"), count=Count("pk"))
        .order_by("-invoiced")
    )
