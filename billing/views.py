from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, StaffRequiredMixin
from core.utils.urls import redirect_next
from core.views import FormPageMixin
from subscriptions.models import Subscription

from . import services
from .forms import BillingRunForm, DiscountForm, InvoiceFilterForm
from .models import Discount, Invoice, InvoiceStatus

# --- Invoices -----------------------------------------------------------------


class InvoiceListView(StaffRequiredMixin, ListView):
    template_name = "billing/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Invoice.objects.select_related("customer", "subscription")
        self.filter_form = InvoiceFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                term = data["q"].strip()
                queryset = queryset.filter(Q(number__icontains=term) | Q(customer_name__icontains=term))
            queryset = services.filter_invoices(queryset, data["state"])
            if data["date_from"]:
                queryset = queryset.filter(invoice_date__gte=data["date_from"])
            if data["date_to"]:
                queryset = queryset.filter(invoice_date__lte=data["date_to"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        open_invoices = Invoice.objects.filter(status=InvoiceStatus.CONFIRMED)
        context["summary"] = {
            "drafts": Invoice.objects.filter(status=InvoiceStatus.DRAFT).count(),
            "outstanding": open_invoices.aggregate(total=Sum("amount_total"), paid=Sum("amount_paid")),
            "overdue": open_invoices.filter(due_date__lt=today).aggregate(n=Count("pk"), total=Sum("amount_total"), paid=Sum("amount_paid")),
        }
        context["filter_form"] = self.filter_form
        return context


class InvoiceDetailView(StaffRequiredMixin, DetailView):
    template_name = "billing/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return Invoice.objects.select_related("customer", "subscription__plan").prefetch_related("lines", "applied_discounts")


class InvoicePrintView(InvoiceDetailView):
    template_name = "billing/invoice_print.html"


class InvoiceActionView(StaffRequiredMixin, View):
    ACTIONS = {"confirm": services.confirm_invoice, "cancel": services.cancel_invoice, "send": services.send_invoice}

    def post(self, request, pk, action):
        invoice = get_object_or_404(Invoice, pk=pk)
        handler = self.ACTIONS.get(action)
        if handler is None:
            raise Http404
        try:
            if action == "send":
                handler(invoice, request=request)
                messages.success(request, f"{invoice.number} emailed to {invoice.customer_email}.")
            else:
                handler(invoice)
                messages.success(request, f"{invoice.number} is now {invoice.get_status_display().lower()}.")
        except services.BillingError as error:
            messages.error(request, str(error))
        return redirect_next(request, invoice.get_absolute_url())


class ConfirmDraftsView(StaffRequiredMixin, View):
    def post(self, request):
        drafts = list(Invoice.objects.filter(status=InvoiceStatus.DRAFT))
        for invoice in drafts:
            services.confirm_invoice(invoice)
        messages.success(request, f"{len(drafts)} draft invoice(s) confirmed.")
        return redirect("billing:invoice_list")


# --- Billing run ---------------------------------------------------------------


class BillingRunView(StaffRequiredMixin, FormView):
    template_name = "billing/billing_run.html"
    form_class = BillingRunForm

    def get_initial(self):
        return {"run_date": timezone.localdate()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context["due"] = services.due_subscriptions(today).select_related("customer").order_by("next_invoice_date")[:20]
        context["due_count"] = services.due_subscriptions(today).count()
        context["starting_count"] = Subscription.objects.filter(status="confirmed", start_date__lte=today).count()
        return context

    def form_valid(self, form):
        result = services.run_billing(form.cleaned_data["run_date"], auto_confirm=form.cleaned_data["auto_confirm"])
        if result.invoices:
            messages.success(
                self.request,
                f"Billing run for {result.run_date:%d %b %Y}: {len(result.invoices)} invoice(s) created "
                f"({result.invoiced_amount:,.2f} {settings.CURRENCY_CODE}).",
            )
        else:
            messages.info(self.request, f"Billing run for {result.run_date:%d %b %Y}: nothing was due. No invoice was created twice.")
        if result.activated or result.closed:
            messages.info(self.request, f"{result.activated} subscription(s) activated, {result.closed} closed at expiry.")
        for error in result.errors:
            messages.warning(self.request, error)
        return self.render_to_response(self.get_context_data(form=form, result=result))


class SubscriptionInvoiceNowView(StaffRequiredMixin, View):
    """'Create invoice' button on a subscription: bills every period due today."""

    def post(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        try:
            invoices = services.bill_subscription(subscription)
        except services.BillingError as error:
            messages.error(request, str(error))
            return redirect(subscription)
        if not invoices:
            when = f"{subscription.next_invoice_date:%d %b %Y}" if subscription.next_invoice_date else "-"
            messages.info(request, f"Nothing to invoice yet; the next period starts on {when}.")
            return redirect(subscription)
        messages.success(request, f"{len(invoices)} invoice(s) created.")
        return redirect(invoices[-1])


class SubscriptionDiscountView(StaffRequiredMixin, View):
    """Attach or detach a discount rule (rules themselves are admin-only)."""

    def post(self, request, pk):
        subscription = get_object_or_404(Subscription, pk=pk)
        discount = get_object_or_404(Discount, pk=request.POST.get("discount"))
        if request.POST.get("remove"):
            discount.subscriptions.remove(subscription)
            messages.success(request, f"{discount.name} removed from {subscription.number}.")
        else:
            discount.subscriptions.add(subscription)
            messages.success(request, f"{discount.name} will apply automatically on the next invoices while it is valid.")
        return redirect(subscription)


# --- Discounts (admin) -------------------------------------------------------------


class DiscountListView(AdminRequiredMixin, ListView):
    template_name = "billing/discount_list.html"
    context_object_name = "discounts"

    def get_queryset(self):
        return Discount.objects.annotate(subscription_count=Count("subscriptions", distinct=True)).order_by("name")


class DiscountFormMixin(AdminRequiredMixin, FormPageMixin, SuccessMessageMixin):
    model = Discount
    form_class = DiscountForm
    success_url = reverse_lazy("billing:discount_list")
    success_message = "Discount %(name)s saved."
    section, singular, cancel_url = "Discounts", "discount", reverse_lazy("billing:discount_list")
    form_hint = "Fixed or percentage, for whole subscriptions or specific products, with conditions and a usage limit."
    form_width = "col-xl-8"

    def get_cancel_url(self):
        return self.cancel_url


class DiscountCreateView(DiscountFormMixin, CreateView):
    pass


class DiscountUpdateView(DiscountFormMixin, UpdateView):
    pass
