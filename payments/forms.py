from django import forms
from django.utils import timezone

from core.forms import BootstrapFormMixin, DateInput

from .models import Payment, PaymentMethod


class PaymentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ("amount", "method", "payment_date", "reference", "note")
        widgets = {"payment_date": DateInput()}

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        if invoice is not None:
            self.fields["amount"].help_text = f"Amount due: {invoice.amount_due:,.2f}"
            self.fields["amount"].widget.attrs["max"] = str(invoice.amount_due)

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if self.invoice is not None and amount > self.invoice.amount_due:
            raise forms.ValidationError(f"Cannot exceed the amount due ({self.invoice.amount_due:,.2f}).")
        return amount

    def clean_payment_date(self):
        value = self.cleaned_data["payment_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("The payment date cannot be in the future.")
        return value


class PaymentFilterForm(BootstrapFormMixin, forms.Form):
    q = forms.CharField(label="Search", widget=forms.TextInput(attrs={"placeholder": "Payment, invoice or customer"}))
    method = forms.ChoiceField(choices=[("", "Any method"), *PaymentMethod.choices])
    date_from = forms.DateField(label="Paid from", widget=DateInput())
    date_to = forms.DateField(label="Paid until", widget=DateInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop("required", None)
            field.widget.attrs["class"] += " form-select-sm" if isinstance(field.widget, forms.Select) else " form-control-sm"
