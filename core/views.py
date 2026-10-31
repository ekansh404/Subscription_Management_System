from django.apps import apps
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView, TemplateView

from .mixins import AdminRequiredMixin
from .models import OutboxEmail
from .navigation import menu_for


class HomeView(LoginRequiredMixin, TemplateView):
    """
    Landing page after login.

    Customers go to their portal and staff to the reports dashboard when those
    modules are installed; otherwise a launchpad lists the available modules.
    """

    template_name = "core/home.html"

    def get(self, request, *args, **kwargs):
        user = request.user
        if user.is_customer and apps.is_installed("portal"):
            return redirect("portal:home")
        if user.is_staff_member and apps.is_installed("reports"):
            return redirect("reports:dashboard")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["modules"] = menu_for(self.request.user)
        return context


class OutboxListView(AdminRequiredMixin, ListView):
    """Emails the app has sent while EMAIL_BACKEND=outbox (demo / offline mode)."""

    model = OutboxEmail
    template_name = "core/outbox_list.html"
    context_object_name = "emails"
    paginate_by = settings.PAGINATE_BY

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["outbox_active"] = settings.EMAIL_BACKEND == "core.mail.OutboxEmailBackend"
        return context


class OutboxDetailView(AdminRequiredMixin, DetailView):
    model = OutboxEmail
    template_name = "core/outbox_detail.html"
    context_object_name = "email"


def healthcheck(request):
    """Lightweight liveness endpoint for uptime monitors and deployment checks."""
    return JsonResponse({"status": "ok"})


class FormPageMixin:
    """
    Context for ``partials/_generic_form.html``: set ``section`` (sidebar
    title), ``singular`` (noun used in headings) and ``cancel_url``.
    """

    template_name = "partials/_generic_form.html"
    section = ""
    singular = ""
    form_hint = ""
    form_width = ""
    cancel_url = None

    def get_cancel_url(self):
        if getattr(self, "object", None) is not None and hasattr(self.object, "get_absolute_url"):
            return self.object.get_absolute_url()
        return self.cancel_url

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            section=self.section,
            singular=self.singular,
            form_hint=self.form_hint,
            form_width=self.form_width,
            cancel_url=self.get_cancel_url(),
        )
        return context
