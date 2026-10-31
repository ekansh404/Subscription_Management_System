from django import forms

from core.forms import BootstrapFormMixin

from .models import Customer


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            "name",
            "company",
            "email",
            "phone",
            "tax_id",
            "street",
            "city",
            "state",
            "postal_code",
            "country",
            "notes",
            "is_active",
        )
        labels = {"is_active": "Active customer"}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Customer.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A customer with this email already exists.")
        return email


class CustomerFilterForm(BootstrapFormMixin, forms.Form):
    STATUS_CHOICES = [("", "All"), ("active", "Active"), ("inactive", "Inactive")]
    PORTAL_CHOICES = [("", "All"), ("yes", "Has portal login"), ("no", "No portal login")]

    q = forms.CharField(label="Search", required=False, widget=forms.TextInput(attrs={"placeholder": "Name, email, phone, GSTIN"}))
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    portal = forms.ChoiceField(label="Portal", choices=PORTAL_CHOICES, required=False)
    city = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.pop("required", None)
            field.widget.attrs["class"] += " form-control-sm" if not isinstance(field.widget, forms.Select) else " form-select-sm"
