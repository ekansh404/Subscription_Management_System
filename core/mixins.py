"""
Role-based access control for views.

Three roles exist (see ``accounts.models.Role``):

* ``admin``    - controls the whole system (products, plans, taxes, discounts, staff)
* ``staff``    - internal team: customers, subscriptions, invoices, payments, reports
* ``customer`` - sees only their own subscriptions and invoices (portal)

Anonymous users are redirected to the login page; authenticated users without
the required role receive a 403.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .navigation import ADMIN, CUSTOMER, STAFF


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles: tuple[str, ...] = ()

    def test_func(self) -> bool:
        return self.request.user.role in self.allowed_roles


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = (ADMIN,)


class StaffRequiredMixin(RoleRequiredMixin):
    """Admins are staff too: anything staff can do, an admin can do."""

    allowed_roles = (ADMIN, STAFF)


class CustomerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (CUSTOMER,)


def role_required(*roles: str):
    """Function-view counterpart of the mixins above."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


staff_required = role_required(ADMIN, STAFF)
admin_required = role_required(ADMIN)
customer_required = role_required(CUSTOMER)
