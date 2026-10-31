from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from core.mixins import AdminRequiredMixin, StaffRequiredMixin

from . import services
from .forms import (
    FromTemplateForm,
    QuotationTemplateForm,
    SubscriptionFilterForm,
    SubscriptionForm,
    SubscriptionLineFormSet,
    TemplateLineFormSet,
)
from .models import QuotationTemplate, Status, Subscription

ACTION_BUTTONS = {
    "send": ("Send quotation", "btn-outline-primary", "send", ""),
    "confirm": ("Confirm", "btn-primary", "check", ""),
    "activate": ("Activate", "btn-success", "play", ""),
    "pause": ("Pause", "btn-outline-warning", "pause", "Pause this subscription? No invoices are issued while paused."),
    "resume": ("Resume", "btn-success", "play", ""),
    "renew": ("Renew", "btn-outline-success", "refresh", "Extend this subscription by another term?"),
    "close": ("Close", "btn-outline-danger", "x-circle", "Close this subscription? It will no longer be billed."),
}


class SubscriptionListView(StaffRequiredMixin, ListView):
    template_name = "subscriptions/subscription_list.html"
    context_object_name = "subscriptions"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Subscription.objects.select_related("customer", "plan")
        self.filter_form = SubscriptionFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                term = data["q"].strip()
                queryset = queryset.filter(
                    Q(number__icontains=term) | Q(customer__name__icontains=term) | Q(customer__company__icontains=term)
                )
            if data["status"]:
                queryset = queryset.filter(status=data["status"])
            if data["plan"]:
                queryset = queryset.filter(plan=data["plan"])
            if data["start_from"]:
                queryset = queryset.filter(start_date__gte=data["start_from"])
            if data["start_to"]:
                queryset = queryset.filter(start_date__lte=data["start_to"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = dict(Subscription.objects.values_list("status").annotate(n=Count("pk")).order_by())
        context["status_counts"] = [(code, label, counts.get(code, 0)) for code, label in Status.choices]
        context["current_status"] = self.request.GET.get("status", "")
        context["filter_form"] = self.filter_form
        context["template_form"] = FromTemplateForm(initial={"start_date": timezone.localdate()})
        return context


class SubscriptionDetailView(StaffRequiredMixin, DetailView):
    template_name = "subscriptions/subscription_detail.html"
    context_object_name = "subscription"

    def get_queryset(self):
        return Subscription.objects.select_related("customer", "plan", "template", "salesperson").prefetch_related(
            "lines__variant__product", "lines__taxes", "events__user"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["actions"] = [
            (name, *ACTION_BUTTONS[name]) for name in services.available_actions(self.object)
        ]
        # Billing data through reverse relations (the billing app builds on this one).
        if apps.is_installed("billing"):
            context["invoices"] = self.object.invoices.all()[:24]
            Discount = apps.get_model("billing", "Discount")
            context["available_discounts"] = Discount.objects.filter(is_active=True).exclude(subscriptions=self.object)
        return context


class SubscriptionEditView(StaffRequiredMixin, TemplateView):
    """Create (no pk) or edit a draft/quotation together with its product lines."""

    template_name = "subscriptions/subscription_form.html"

    def get_object(self):
        if "pk" not in self.kwargs:
            return None
        subscription = get_object_or_404(Subscription, pk=self.kwargs["pk"])
        if not subscription.is_editable:
            raise Http404("Only draft subscriptions and quotations can be edited.")
        return subscription

    def get_context_data(self, form=None, formset=None, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object = getattr(self, "object", None) or self.get_object()
        initial = {} if self.object else {"start_date": timezone.localdate(), "salesperson": self.request.user}
        if self.request.GET.get("customer"):
            initial["customer"] = self.request.GET["customer"]
        context["object"] = self.object
        context["form"] = form or SubscriptionForm(instance=self.object, initial=initial)
        context["formset"] = formset or SubscriptionLineFormSet(instance=self.object or Subscription())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = SubscriptionForm(request.POST, instance=self.object)
        formset = SubscriptionLineFormSet(request.POST, instance=self.object or Subscription())
        if not (form.is_valid() and formset.is_valid()):
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        with transaction.atomic():
            if self.object is None:
                data = form.cleaned_data
                has_lines = any(f.cleaned_data and not f.cleaned_data.get("DELETE") for f in formset.forms)
                subscription = services.create_subscription(
                    data["customer"],
                    data["plan"],
                    start_date=data["start_date"],
                    user=request.user,
                    with_plan_line=not has_lines,
                    expiry_date=data["expiry_date"],
                    payment_term_days=data["payment_term_days"],
                    notes=data["notes"],
                )
                subscription.salesperson = data["salesperson"]
                subscription.save(update_fields=["salesperson"])
            else:
                subscription = form.save()
                services.log(subscription, "Quotation edited.", user=request.user)
            formset.instance = subscription
            formset.save()
            services.recompute_totals(subscription)
        messages.success(request, f"{subscription.number} saved.")
        return redirect(subscription)


class SubscriptionFromTemplateView(StaffRequiredMixin, FormView):
    form_class = FromTemplateForm
    template_name = "partials/_generic_form.html"

    def form_valid(self, form):
        data = form.cleaned_data
        subscription = services.create_subscription(
            data["customer"], data["template"].plan, start_date=data["start_date"], template=data["template"], user=self.request.user
        )
        messages.success(self.request, f"{subscription.number} created from {data['template'].name}. Review the lines, then send or confirm.")
        return redirect(subscription)

    def form_invalid(self, form):
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return redirect("subscriptions:subscription_list")


class SubscriptionActionView(StaffRequiredMixin, View):
    """POST /subscriptions/<pk>/<action>/ for every lifecycle button."""

    def post(self, request, pk, action):
        subscription = get_object_or_404(Subscription.objects.select_related("plan", "template"), pk=pk)
        handler = services.ACTIONS.get(action)
        if handler is None:
            raise Http404
        kwargs = {"user": request.user}
        if action == "close":
            kwargs["reason"] = request.POST.get("reason", "").strip()
        try:
            handler(subscription, **kwargs)
        except services.TransitionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"{subscription.number}: {subscription.get_status_display()}.")
        return redirect(request.POST.get("next") or subscription.get_absolute_url())


# --- Quotation templates -----------------------------------------------------


class TemplateListView(StaffRequiredMixin, ListView):
    template_name = "subscriptions/template_list.html"
    context_object_name = "templates"

    def get_queryset(self):
        return (
            QuotationTemplate.objects.select_related("plan")
            .annotate(line_count=Count("lines", distinct=True), use_count=Count("subscriptions", distinct=True))
            .order_by("name")
        )


class TemplateEditView(AdminRequiredMixin, TemplateView):
    template_name = "subscriptions/template_form.html"
    success_url = reverse_lazy("subscriptions:template_list")

    def get_object(self):
        if "pk" not in self.kwargs:
            return None
        return get_object_or_404(QuotationTemplate, pk=self.kwargs["pk"])

    def get_context_data(self, form=None, formset=None, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        context["object"] = obj
        context["form"] = form or QuotationTemplateForm(instance=obj)
        context["formset"] = formset or TemplateLineFormSet(instance=obj or QuotationTemplate())
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        form = QuotationTemplateForm(request.POST, instance=obj)
        formset = TemplateLineFormSet(request.POST, instance=obj or QuotationTemplate())
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                template = form.save()
                formset.instance = template
                formset.save()
            messages.success(request, f"Template {template.name} saved.")
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))
