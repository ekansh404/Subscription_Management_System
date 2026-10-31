from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import StaffRequiredMixin

from .forms import CustomerFilterForm, CustomerForm
from .models import Customer
from .services import attach_existing_login


class CustomerListView(StaffRequiredMixin, ListView):
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Customer.objects.select_related("user")
        self.filter_form = CustomerFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                term = data["q"].strip()
                queryset = queryset.filter(
                    Q(name__icontains=term)
                    | Q(company__icontains=term)
                    | Q(email__icontains=term)
                    | Q(phone__icontains=term)
                    | Q(tax_id__icontains=term)
                )
            if data["status"]:
                queryset = queryset.filter(is_active=data["status"] == "active")
            if data["portal"]:
                queryset = queryset.filter(user__isnull=data["portal"] == "no")
            if data["city"]:
                queryset = queryset.filter(city__icontains=data["city"].strip())
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class CustomerDetailView(StaffRequiredMixin, DetailView):
    model = Customer
    template_name = "customers/customer_detail.html"
    context_object_name = "customer"

    def get_queryset(self):
        return Customer.objects.select_related("user")


class CustomerCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_message = "Customer %(name)s created."

    def form_valid(self, form):
        response = super().form_valid(form)
        if attach_existing_login(self.object):
            messages.info(self.request, "An existing portal login with this email was linked automatically.")
        return response


class CustomerUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_message = "Customer %(name)s updated."


class CustomerLinkLoginView(StaffRequiredMixin, View):
    """Link a customer to a portal account that signed up with the same email."""

    def post(self, request, pk):
        customer = get_object_or_404(Customer, pk=pk)
        if attach_existing_login(customer):
            messages.success(request, f"Portal login {customer.email} linked to {customer.name}.")
        else:
            messages.warning(
                request,
                "No unlinked portal account uses this email yet. Ask the customer to sign up with "
                f"{customer.email}; it will be linked automatically.",
            )
        return redirect(customer)
