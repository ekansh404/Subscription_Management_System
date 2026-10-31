from django import forms

from core.forms import BootstrapFormMixin, DateInput

from .models import Discount, DiscountScope, InvoiceStatus

PAYMENT_STATE_CHOICES = [
    ("", "Any state"),
    ("draft", "Draft"),
    ("due", "Due"),
    ("partial", "Partially paid"),
    ("overdue", "Overdue"),
    ("outstanding", "Outstanding (due + partial + overdue)"),
    ("paid", "Paid"),
    ("cancelled", "Cancelled"),
]


class DiscountForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Discount
        fields = (
            "name",
            "code",
            "discount_type",
            "value",
            "scope",
            "products",
            "min_purchase",
            "min_quantity",
            "start_date",
            "end_date",
            "usage_limit",
            "is_active",
        )
        widgets = {"start_date": DateInput(), "end_date": DateInput(), "products": forms.CheckboxSelectMultiple}
        labels = {"products": "Products (when it applies to specific products)"}

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("scope") == DiscountScope.PRODUCTS and not cleaned.get("products"):
            self.add_error("products", "Pick at least one product, or apply it to the whole subscription.")
        return cleaned


class InvoiceFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Search", widget=forms.TextInput(attrs={"placeholder": "Number or customer"}))
    state = forms.ChoiceField(label="State", choices=PAYMENT_STATE_CHOICES)
    date_from = forms.DateField(label="Invoiced from", widget=DateInput())
    date_to = forms.DateField(label="Invoiced until", widget=DateInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop("required", None)
            field.widget.attrs["class"] += " form-select-sm" if isinstance(field.widget, forms.Select) else " form-control-sm"


class BillingRunForm(BootstrapFormMixin, forms.Form):
    run_date = forms.DateField(label="Billing date", widget=DateInput(), help_text="Bill everything due up to this date.")
    auto_confirm = forms.BooleanField(label="Confirm the new invoices straight away", required=False)


INVOICE_STATUS_VALUES = [code for code, _ in InvoiceStatus.choices]
