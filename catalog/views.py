from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, StaffRequiredMixin
from core.views import FormPageMixin

from .forms import AttributeForm, AttributeValueFormSet, PlanFilterForm, PlanForm, ProductFilterForm, ProductForm, TaxForm
from .models import AttributeValue, Plan, Product, ProductAttribute, ProductVariant, Tax
from .services import generate_variants

# --- Taxes (admin) -----------------------------------------------------------


class TaxListView(AdminRequiredMixin, ListView):
    model = Tax
    template_name = "catalog/tax_list.html"
    context_object_name = "taxes"

    def get_queryset(self):
        return Tax.objects.annotate(product_count=Count("products")).order_by("name")


class TaxFormMixin(AdminRequiredMixin, FormPageMixin, SuccessMessageMixin):
    model = Tax
    form_class = TaxForm
    success_url = reverse_lazy("catalog:tax_list")
    success_message = "Tax %(name)s created."
    section, singular, cancel_url = "Taxes", "tax", reverse_lazy("catalog:tax_list")
    form_hint = "Taxes are applied per invoice line from the product's default taxes."


class TaxCreateView(TaxFormMixin, CreateView):
    pass


class TaxUpdateView(TaxFormMixin, UpdateView):
    success_message = "Tax %(name)s updated."

    def get_cancel_url(self):
        return self.cancel_url


# --- Attributes (admin) ------------------------------------------------------


class AttributeListView(AdminRequiredMixin, ListView):
    template_name = "catalog/attribute_list.html"
    context_object_name = "attributes"

    def get_queryset(self):
        return ProductAttribute.objects.prefetch_related("values")


class AttributeFormView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    """Create or edit an attribute together with its values (inline formset)."""

    model = ProductAttribute
    form_class = AttributeForm
    template_name = "catalog/attribute_form.html"
    success_url = reverse_lazy("catalog:attribute_list")
    success_message = "Attribute %(name)s saved."

    def get_object(self, queryset=None):
        if "pk" not in self.kwargs:
            return None
        return super().get_object(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "formset" not in context:
            context["formset"] = AttributeValueFormSet(instance=self.object or ProductAttribute())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = AttributeValueFormSet(request.POST, instance=self.object or ProductAttribute())
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                self.object = form.save()
                formset.instance = self.object
                formset.save()
                # Price extras may have changed: refresh the variants that use them.
                for product in Product.objects.filter(attribute_values__attribute=self.object).distinct():
                    generate_variants(product)
            messages.success(request, self.get_success_message(form.cleaned_data))
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))


# --- Products ----------------------------------------------------------------


class ProductListView(StaffRequiredMixin, ListView):
    template_name = "catalog/product_list.html"
    context_object_name = "products"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Product.objects.annotate(
            variant_count=Count("variants", filter=Q(variants__is_active=True), distinct=True)
        ).prefetch_related("taxes").order_by("name")
        self.filter_form = ProductFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                queryset = queryset.filter(name__icontains=data["q"].strip())
            if data["product_type"]:
                queryset = queryset.filter(product_type=data["product_type"])
            if data["status"]:
                queryset = queryset.filter(is_active=data["status"] == "active")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class ProductDetailView(StaffRequiredMixin, DetailView):
    model = Product
    template_name = "catalog/product_detail.html"
    context_object_name = "product"

    def get_queryset(self):
        return Product.objects.prefetch_related(
            "taxes",
            Prefetch("variants", queryset=ProductVariant.objects.prefetch_related("values__attribute")),
            Prefetch("attribute_values", queryset=AttributeValue.objects.select_related("attribute")),
        )


class ProductFormMixin(AdminRequiredMixin, FormPageMixin, SuccessMessageMixin):
    model = Product
    form_class = ProductForm
    success_message = "Product %(name)s saved."
    section, singular, cancel_url = "Products", "product", reverse_lazy("catalog:product_list")
    form_hint = "Tick variant options (for example Brand: Odoo) and one variant is generated per combination."

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            variants = generate_variants(self.object)
        if len(variants) > 1:
            messages.info(self.request, f"{len(variants)} variants are available for sale.")
        return response


class ProductCreateView(ProductFormMixin, CreateView):
    pass


class ProductUpdateView(ProductFormMixin, UpdateView):
    pass


# --- Plans -------------------------------------------------------------------


class PlanListView(StaffRequiredMixin, ListView):
    template_name = "catalog/plan_list.html"
    context_object_name = "plans"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = Plan.objects.select_related("product")
        self.filter_form = PlanFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["q"]:
                queryset = queryset.filter(name__icontains=data["q"].strip())
            if data["billing_period"]:
                queryset = queryset.filter(billing_period=data["billing_period"])
            if data["status"] == "inactive":
                queryset = queryset.filter(is_active=False)
            elif data["status"] == "available":
                today = date.today()
                queryset = queryset.filter(is_active=True).filter(
                    Q(start_date__isnull=True) | Q(start_date__lte=today),
                    Q(end_date__isnull=True) | Q(end_date__gte=today),
                )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["today"] = date.today()
        return context


class PlanDetailView(StaffRequiredMixin, DetailView):
    model = Plan
    template_name = "catalog/plan_detail.html"
    context_object_name = "plan"

    def get_queryset(self):
        return Plan.objects.select_related("product__product")


class PlanFormMixin(AdminRequiredMixin, FormPageMixin, SuccessMessageMixin):
    model = Plan
    form_class = PlanForm
    success_message = "Plan %(name)s saved."
    section, singular, cancel_url = "Plans", "plan", reverse_lazy("catalog:plan_list")
    form_hint = "Price per billing period, minimum quantity, availability dates and lifecycle options."
    form_width = "col-xl-8"


class PlanCreateView(PlanFormMixin, CreateView):
    pass


class PlanUpdateView(PlanFormMixin, UpdateView):
    pass
