from django import forms
from django.forms import inlineformset_factory

from catalog.models import Plan, ProductVariant, Tax
from core.forms import BootstrapFormMixin, DateInput
from core.widgets import DataAttributeSelect, DataAttributeSelectMultiple
from customers.models import Customer

from .models import QuotationTemplate, QuotationTemplateLine, Status, Subscription, SubscriptionLine


def sellable_variants():
    return ProductVariant.objects.filter(is_active=True).select_related("product").prefetch_related("product__taxes")


class SubscriptionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ("customer", "plan", "start_date", "expiry_date", "payment_term_days", "salesperson", "notes")
        widgets = {"start_date": DateInput(), "expiry_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        self.fields["plan"].queryset = Plan.objects.filter(is_active=True)
        self.fields["salesperson"].queryset = self.fields["salesperson"].queryset.filter(role__in=["admin", "staff"])

    def clean(self):
        cleaned = super().clean()
        start, expiry, plan = cleaned.get("start_date"), cleaned.get("expiry_date"), cleaned.get("plan")
        if start and expiry and expiry <= start:
            self.add_error("expiry_date", "The expiry date must be after the start date.")
        if plan and start and not plan.is_available(start):
            self.add_error("plan", f"{plan.name} is not available on {start:%d %b %Y}.")
        return cleaned


class FromTemplateForm(BootstrapFormMixin, forms.Form):
    template = forms.ModelChoiceField(queryset=QuotationTemplate.objects.filter(is_active=True).select_related("plan"))
    customer = forms.ModelChoiceField(queryset=Customer.objects.filter(is_active=True))
    start_date = forms.DateField(widget=DateInput())

    def clean(self):
        cleaned = super().clean()
        template, start = cleaned.get("template"), cleaned.get("start_date")
        if template and start and not template.plan.is_available(start):
            self.add_error("start_date", f"{template.plan.name} is not available on {start:%d %b %Y}.")
        return cleaned


class LineForm(BootstrapFormMixin, forms.ModelForm):
    """Product line; the selects carry data-* so the page recalculates totals live."""

    class Meta:
        model = SubscriptionLine
        fields = ("variant", "quantity", "unit_price", "taxes")
        widgets = {
            "variant": DataAttributeSelect(data_attrs={"price": "price", "taxes": "tax_ids"}),
            "taxes": DataAttributeSelectMultiple(data_attrs={"rate": "rate"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["variant"].queryset = sellable_variants()
        if "taxes" in self.fields:
            self.fields["taxes"].queryset = Tax.objects.filter(is_active=True)
            self.fields["taxes"].required = False
            self.fields["taxes"].widget.attrs.pop("required", None)
        for name, field in self.fields.items():
            field.widget.attrs["data-field"] = name
            field.widget.attrs["class"] += " form-control-sm" if name in ("quantity", "unit_price") else " form-select-sm"


SubscriptionLineFormSet = inlineformset_factory(
    Subscription, SubscriptionLine, form=LineForm, extra=0, can_delete=True
)


class SubscriptionFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Search", widget=forms.TextInput(attrs={"placeholder": "Number or customer"}))
    status = forms.ChoiceField(choices=[("", "Any status"), *Status.choices])
    plan = forms.ModelChoiceField(queryset=Plan.objects.all(), empty_label="Any plan")
    start_from = forms.DateField(label="Starts from", widget=DateInput())
    start_to = forms.DateField(label="Starts until", widget=DateInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop("required", None)
            field.widget.attrs["class"] += " form-select-sm" if isinstance(field.widget, forms.Select) else " form-control-sm"


class QuotationTemplateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = QuotationTemplate
        fields = ("name", "plan", "validity_days", "duration_periods", "payment_term_days", "notes", "is_active")
        labels = {"is_active": "Active (can be used for new quotations)"}


class TemplateLineForm(LineForm):
    class Meta:
        model = QuotationTemplateLine
        fields = ("variant", "quantity", "unit_price")
        widgets = {"variant": DataAttributeSelect(data_attrs={"price": "price"})}


TemplateLineFormSet = inlineformset_factory(
    QuotationTemplate, QuotationTemplateLine, form=TemplateLineForm, extra=0, can_delete=True, min_num=1, validate_min=True
)
