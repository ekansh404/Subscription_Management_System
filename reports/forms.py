from django import forms

from catalog.models import Plan
from core.forms import BootstrapFormMixin, DateInput
from customers.models import Customer


class ReportFilterForm(BootstrapFormMixin, forms.Form):
    date_from = forms.DateField(label="From", widget=DateInput())
    date_to = forms.DateField(label="To", widget=DateInput())
    plan = forms.ModelChoiceField(queryset=Plan.objects.all(), empty_label="All plans")
    customer = forms.ModelChoiceField(queryset=Customer.objects.all(), empty_label="All customers")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
            field.widget.attrs.pop("required", None)
            field.widget.attrs["class"] += " form-select-sm" if isinstance(field.widget, forms.Select) else " form-control-sm"

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("date_from") and cleaned.get("date_to") and cleaned["date_to"] < cleaned["date_from"]:
            raise forms.ValidationError("The end date must be after the start date.")
        return cleaned
