from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import AdminRequiredMixin

from .forms import (
    LoginForm,
    PasswordChangeForm,
    PasswordResetForm,
    ProfileForm,
    SetPasswordForm,
    SignupForm,
    StaffCreateForm,
    StaffUpdateForm,
)
from .models import Role, User


class SignupView(CreateView):
    """A new customer creates an account with their email and a password."""

    form_class = SignupForm
    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)
        messages.success(self.request, f"Welcome to {settings.APP_NAME}, {user.first_name}! Your account is ready.")
        return redirect("core:home")


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    form_class = PasswordResetForm
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    # Without this Django names the site after the host (e.g. "127.0.0.1:8000").
    extra_email_context = {"site_name": settings.APP_NAME}


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = SetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change_form.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("accounts:profile")
    success_message = "Your password has been changed."


class ProfileView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    form_class = ProfileForm
    template_name = "accounts/profile.html"
    success_url = reverse_lazy("accounts:profile")
    success_message = "Profile updated."

    def get_object(self, queryset=None):
        return self.request.user


# --- Staff management (admin only) -----------------------------------------


class StaffQuerysetMixin:
    def get_queryset(self):
        return User.objects.filter(role__in=[Role.STAFF, Role.ADMIN]).order_by("first_name", "last_name")


class StaffListView(AdminRequiredMixin, StaffQuerysetMixin, ListView):
    template_name = "accounts/staff_list.html"
    context_object_name = "members"
    paginate_by = settings.PAGINATE_BY

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "")
        return context


class StaffCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    form_class = StaffCreateForm
    template_name = "accounts/staff_form.html"
    success_url = reverse_lazy("accounts:staff_list")
    success_message = "%(first_name)s %(last_name)s has been added to the team."


class StaffUpdateView(AdminRequiredMixin, StaffQuerysetMixin, SuccessMessageMixin, UpdateView):
    form_class = StaffUpdateForm
    template_name = "accounts/staff_form.html"
    success_url = reverse_lazy("accounts:staff_list")
    success_message = "Team member updated."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["editor"] = self.request.user
        return kwargs
