import logging
import smtplib
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from billing.models import Invoice, InvoiceStatus
from core.mixins import StaffRequiredMixin
from core.utils.urls import redirect_next

from .forms import PaymentFilterForm, PaymentForm
from .models import Payment, PaymentMethod
from .services import PaymentError, record_payment

logger = logging.getLogger(__name__)


class PaymentListView(StaffRequiredMixin, ListView):
    template_name = "payments/payment_list.html"
    context_object_name = "payments"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Payment.objects.select_related("invoice", "customer")
        self.filter_form = PaymentFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                term = data["q"].strip()
                queryset = queryset.filter(
                    Q(number__icontains=term) | Q(invoice__number__icontains=term) | Q(customer__name__icontains=term)
                )
            if data["method"]:
                queryset = queryset.filter(method=data["method"])
            if data["date_from"]:
                queryset = queryset.filter(payment_date__gte=data["date_from"])
            if data["date_to"]:
                queryset = queryset.filter(payment_date__lte=data["date_to"])
        self.filtered = queryset
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["totals"] = self.filtered.aggregate(total=Sum("amount"), n=Count("pk"))
        context["by_method"] = [
            {**row, "label": PaymentMethod(row["method"]).label}
            for row in self.filtered.values("method").annotate(total=Sum("amount"), n=Count("pk")).order_by("-total")
        ]
        return context


class RecordPaymentView(StaffRequiredMixin, FormView):
    template_name = "payments/payment_form.html"
    form_class = PaymentForm

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(Invoice, pk=kwargs["invoice_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["invoice"] = self.invoice
        return kwargs

    def get_initial(self):
        return {"amount": self.invoice.amount_due, "payment_date": timezone.localdate()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoice"] = self.invoice
        return context

    def form_valid(self, form):
        try:
            payment = record_payment(self.invoice, user=self.request.user, **form.cleaned_data)
        except PaymentError as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        self.invoice.refresh_from_db()
        state = "Invoice fully paid." if self.invoice.status == InvoiceStatus.PAID else f"{self.invoice.amount_due:,.2f} still due."
        messages.success(self.request, f"Payment {payment.number} recorded. {state}")
        return redirect(self.invoice)


class PaymentReceiptView(StaffRequiredMixin, DetailView):
    template_name = "payments/payment_receipt.html"
    context_object_name = "payment"

    def get_queryset(self):
        return Payment.objects.select_related("invoice", "customer", "recorded_by")


def aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "Not yet due"
    if days_overdue <= 30:
        return "1–30 days overdue"
    if days_overdue <= 60:
        return "31–60 days overdue"
    return "60+ days overdue"


class ReceivablesView(StaffRequiredMixin, TemplateView):
    """Outstanding invoices grouped by how late they are, so overdue ones get chased first."""

    template_name = "payments/receivables.html"
    ROWS_PER_BUCKET = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        open_invoices = (
            Invoice.objects.filter(status=InvoiceStatus.CONFIRMED)
            .select_related("customer")
            .annotate(due=F("amount_total") - F("amount_paid"))
            .only("pk", "number", "customer_name", "due_date", "amount_total", "amount_paid", "customer_id")
            .order_by("due_date")
        )
        buckets = OrderedDict((name, {"invoices": [], "count": 0, "total": Decimal("0")}) for name in
                              ("60+ days overdue", "31–60 days overdue", "1–30 days overdue", "Not yet due"))
        for invoice in open_invoices:
            bucket = buckets[aging_bucket((today - invoice.due_date).days)]
            bucket["count"] += 1
            bucket["total"] += invoice.due
            if len(bucket["invoices"]) < self.ROWS_PER_BUCKET:  # oldest first; the rest via the invoice list
                bucket["invoices"].append(invoice)
        context["buckets"] = buckets
        context["total_outstanding"] = sum((bucket["total"] for bucket in buckets.values()), Decimal("0"))
        context["total_overdue"] = sum((b["total"] for name, b in buckets.items() if name != "Not yet due"), Decimal("0"))
        context["top_debtors"] = (
            open_invoices.filter(due_date__lt=today)
            .values("customer__id", "customer__name")
            .annotate(total=Sum(F("amount_total") - F("amount_paid")), n=Count("pk"))
            .order_by("-total")[:5]
        )
        return context


class SendReminderView(StaffRequiredMixin, View):
    def post(self, request, invoice_pk):
        invoice = get_object_or_404(Invoice, pk=invoice_pk, status=InvoiceStatus.CONFIRMED)
        try:
            send_mail(
                f"Reminder: invoice {invoice.number} is overdue",
                f"Hello {invoice.customer_name},\n\nOur records show {invoice.amount_due:,.2f} {settings.CURRENCY_CODE} is still due on "
                f"invoice {invoice.number} (due {invoice.due_date:%d %b %Y}). Please arrange payment at your earliest convenience.\n\n"
                f"Thank you,\n{settings.APP_NAME} Billing",
                settings.DEFAULT_FROM_EMAIL,
                [invoice.customer_email],
            )
        except (OSError, smtplib.SMTPException):
            logger.exception("Could not email a reminder for %s", invoice.number)
            messages.error(request, "The reminder could not be sent. Check the email settings and try again.")
        else:
            messages.success(request, f"Reminder emailed to {invoice.customer_email}.")
        return redirect_next(request, "payments:receivables")
