from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import password_validation

from core.forms import BootstrapFormMixin

from .models import Role, User

STAFF_ROLE_CHOICES = [(Role.STAFF, Role.STAFF.label), (Role.ADMIN, Role.ADMIN.label)]


class SignupForm(BootstrapFormMixin, auth_forms.UserCreationForm):
    """Customer self-registration: email + password (policy enforced by AUTH_PASSWORD_VALIDATORS)."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "you@company.com"})
        self.fields["password1"].help_text = password_validation.password_validators_help_text_html()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.CUSTOMER
        if commit:
            user.save()
        return user


class LoginForm(BootstrapFormMixin, auth_forms.AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget = forms.EmailInput(
            attrs={"class": "form-control", "autofocus": True, "autocomplete": "email", "placeholder": "you@company.com"}
        )
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})

    def clean(self):
        if self.cleaned_data.get("username"):
            self.cleaned_data["username"] = self.cleaned_data["username"].strip().lower()
        return super().clean()


class PasswordResetForm(BootstrapFormMixin, auth_forms.PasswordResetForm):
    pass


class SetPasswordForm(BootstrapFormMixin, auth_forms.SetPasswordForm):
    pass


class PasswordChangeForm(BootstrapFormMixin, auth_forms.PasswordChangeForm):
    pass


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")


class StaffCreateForm(BootstrapFormMixin, forms.ModelForm):
    """Only administrators can add staff (see StaffCreateView)."""

    role = forms.ChoiceField(choices=STAFF_ROLE_CHOICES, initial=Role.STAFF)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["password1"].help_text = password_validation.password_validators_help_text_html()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two password fields didn't match.")
        return cleaned

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password1")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as error:
                self.add_error("password1", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class StaffUpdateForm(BootstrapFormMixin, forms.ModelForm):
    role = forms.ChoiceField(choices=STAFF_ROLE_CHOICES)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "role", "is_active")
        labels = {"is_active": "Account is active (can sign in)"}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        if self.editor and self.instance.pk == self.editor.pk:
            if cleaned.get("role") != Role.ADMIN:
                self.add_error("role", "You cannot remove your own administrator role.")
            if not cleaned.get("is_active", True):
                self.add_error("is_active", "You cannot deactivate your own account.")
        return cleaned
