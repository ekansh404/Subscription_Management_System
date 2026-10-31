from django import forms
from django.forms import inlineformset_factory

from core.forms import BootstrapFormMixin, DateInput

from .models import AttributeValue, Plan, Product, ProductAttribute, ProductVariant, Tax


class TaxForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Tax
        fields = ("name", "rate", "description", "is_active")
        labels = {"is_active": "Active (can be used on new lines)"}


class AttributeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProductAttribute
        fields = ("name",)


class AttributeValueForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AttributeValue
        fields = ("name", "price_extra", "sequence")


AttributeValueFormSet = inlineformset_factory(
    ProductAttribute, AttributeValue, form=AttributeValueForm, extra=2, can_delete=True, min_num=1, validate_min=True
)


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ("name", "product_type", "sales_price", "cost_price", "taxes", "attribute_values", "notes", "is_active")
        widgets = {"taxes": forms.CheckboxSelectMultiple, "attribute_values": forms.CheckboxSelectMultiple}
        labels = {"attribute_values": "Variant options", "is_active": "Active (can be sold)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["taxes"].queryset = Tax.objects.filter(is_active=True)
        self.fields["attribute_values"].queryset = AttributeValue.objects.select_related("attribute")


class PlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Plan
        fields = (
            "name",
            "product",
            "price",
            "billing_period",
            "min_quantity",
            "start_date",
            "end_date",
            "auto_close",
            "closable",
            "pausable",
            "renewable",
            "description",
            "is_active",
        )
        widgets = {"start_date": DateInput(), "end_date": DateInput()}
        labels = {"product": "Default product", "is_active": "Active (offered on new subscriptions)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = ProductVariant.objects.filter(is_active=True).select_related("product")


class _CompactFilterMixin(BootstrapFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop("required", None)
            small = " form-select-sm" if isinstance(field.widget, forms.Select) else " form-control-sm"
            field.widget.attrs["class"] += small


class ProductFilterForm(_CompactFilterMixin, forms.Form):
    q = forms.CharField(label="Search", widget=forms.TextInput(attrs={"placeholder": "Product name"}))
    product_type = forms.ChoiceField(label="Type", choices=[("", "All types"), *Product._meta.get_field("product_type").choices])
    status = forms.ChoiceField(choices=[("", "All"), ("active", "Active"), ("archived", "Archived")])


class PlanFilterForm(_CompactFilterMixin, forms.Form):
    q = forms.CharField(label="Search", widget=forms.TextInput(attrs={"placeholder": "Plan name"}))
    billing_period = forms.ChoiceField(label="Billing", choices=[("", "Any period"), *Plan._meta.get_field("billing_period").choices])
    status = forms.ChoiceField(choices=[("", "All"), ("available", "Available today"), ("inactive", "Inactive")])
