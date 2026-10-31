"""
Customer portal.

Every queryset here is filtered by the signed-in customer's record, so a
customer can only ever reach their own subscriptions, invoices and payments;
anything else is a 404. Lifecycle actions go through the same services as
the staff screens, so the plan's rules (pausable, closable, renewable)
apply to customers too.
"""

from django.conf import settings
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from billing.models import Invoice, InvoiceStatus
from billing.services import filter_invoices
from core.mixins import CustomerRequiredMixin
from customers.services import customer_for_user, link_portal_account
from payments.models import Payment
from subscriptions import services as subscription_services
from subscriptions.models import RUNNING_STATUSES, Status, Subscription

# What a customer may do themselves (staff-only steps such as sending a quotation are excluded).
CUSTOMER_ACTIONS = {
    "accept": ("Accept quotation", "btn-primary", "check", "Accept this quotation and start the subscription?"),
    "pause": ("Pause", "btn-outline-warning", "pause", "Pause your subscription? You will not be invoiced while paused."),
    "resume": ("Resume", "btn-success", "play", ""),
    "renew": ("Renew", "btn-outline-success", "refresh", "Renew for another term?"),
    "close": ("Cancel subscription", "btn-outline-danger", "x-circle", "Cancel your subscription? It will stop being billed."),
}


class PortalMixin(CustomerRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_customer:
            self.customer = customer_for_user(request.user) or link_portal_account(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["customer"] = self.customer
        return context


def customer_actions(subscription, today=None):
    if subscription.status == Status.QUOTATION:
        return ["accept"]
    staff_actions = subscription_services.available_actions(subscription, today)
    return [name for name in ("pause", "resume", "renew", "close") if name in staff_actions]


class PortalHomeView(PortalMixin, TemplateView):
    template_name = "portal/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        subscriptions = self.customer.subscriptions.select_related("plan")
        invoices = self.customer.invoices.exclude(status=InvoiceStatus.DRAFT)
        open_invoices = invoices.filter(status=InvoiceStatus.CONFIRMED)
        outstanding = open_invoices.aggregate(total=Sum("amount_total"), paid=Sum("amount_paid"))
        overdue = open_invoices.filter(due_date__lt=today).aggregate(total=Sum("amount_total"), paid=Sum("amount_paid"))
        context.update(
            active_count=subscriptions.filter(status__in=RUNNING_STATUSES).count(),
            quotations=subscriptions.filter(status=Status.QUOTATION),
            subscriptions=subscriptions.filter(status__in=[*RUNNING_STATUSES, Status.CONFIRMED])[:5],
            outstanding=(outstanding["total"] or 0) - (outstanding["paid"] or 0),
            overdue=(overdue["total"] or 0) - (overdue["paid"] or 0),
            next_invoice=subscriptions.filter(status=Status.ACTIVE, next_invoice_date__isnull=False).order_by("next_invoice_date").first(),
            recent_invoices=invoices[:5],
        )
        return context


class PortalSubscriptionListView(PortalMixin, ListView):
    template_name = "portal/subscription_list.html"
    context_object_name = "subscriptions"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        # Drafts are internal work in progress; customers see quotations onwards.
        return self.customer.subscriptions.exclude(status=Status.DRAFT).select_related("plan")


class PortalSubscriptionDetailView(PortalMixin, DetailView):
    template_name = "portal/subscription_detail.html"
    context_object_name = "subscription"

    def get_queryset(self):
        return (
            Subscription.objects.filter(customer=self.customer)
            .exclude(status=Status.DRAFT)
            .select_related("plan")
            .prefetch_related("lines__variant", "lines__taxes")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = [(name, *CUSTOMER_ACTIONS[name]) for name in customer_actions(self.object)]
        context["invoices"] = self.object.invoices.exclude(status=InvoiceStatus.DRAFT)[:24]
        return context


class PortalSubscriptionActionView(PortalMixin, View):
    def post(self, request, pk, action):
        subscription = get_object_or_404(Subscription.objects.select_related("plan", "template"), pk=pk, customer=self.customer)
        if action not in customer_actions(subscription):
            messages.error(request, "This action is not available for your subscription.")
            return redirect("portal:subscription_detail", pk=pk)
        handler = subscription_services.confirm if action == "accept" else subscription_services.ACTIONS[action]
        kwargs = {"user": request.user}
        if action == "close":
            kwargs["reason"] = "Cancelled by the customer from the portal"
        try:
            handler(subscription, **kwargs)
        except subscription_services.TransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Done: {subscription.number} is now {subscription.get_status_display().lower()}.")
        return redirect("portal:subscription_detail", pk=pk)


class PortalInvoiceListView(PortalMixin, ListView):
    template_name = "portal/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = self.customer.invoices.exclude(status=InvoiceStatus.DRAFT).select_related("subscription")
        self.state = self.request.GET.get("state", "")
        return filter_invoices(queryset, self.state)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["state"] = self.state
        context["states"] = [("", "All"), ("outstanding", "To pay"), ("overdue", "Overdue"), ("paid", "Paid")]
        return context


class PortalInvoiceDetailView(PortalMixin, DetailView):
    template_name = "portal/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return (
            Invoice.objects.filter(customer=self.customer)
            .exclude(status=InvoiceStatus.DRAFT)
            .select_related("subscription")
            .prefetch_related("lines", "applied_discounts", "payments")
        )


class PortalInvoicePrintView(PortalInvoiceDetailView):
    template_name = "billing/invoice_print.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["back_url"] = self.request.build_absolute_uri("../")
        return context


class PortalPaymentListView(PortalMixin, ListView):
    template_name = "portal/payment_list.html"
    context_object_name = "payments"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        return Payment.objects.filter(customer=self.customer).select_related("invoice")
