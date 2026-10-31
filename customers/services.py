"""
Customer rules that are shared by signup, staff screens and the demo seeder.
"""

from accounts.models import Role, User

from .models import Customer


def customer_for_user(user: User) -> Customer | None:
    """The customer record a portal user acts as (``None`` for staff or unlinked users)."""
    if not getattr(user, "is_authenticated", False) or user.role != Role.CUSTOMER:
        return None
    return Customer.objects.filter(user=user).first()


def link_portal_account(user: User) -> Customer:
    """
    Make sure a customer-role user has a customer record.

    If staff already created a customer with the same email, the login is
    linked to it (so the customer immediately sees the subscriptions staff set
    up for them); otherwise a new customer record is created.
    """
    existing = Customer.objects.filter(user=user).first()
    if existing:
        return existing
    customer = Customer.objects.filter(email=user.email.lower(), user__isnull=True).first()
    if customer is None:
        customer = Customer(email=user.email.lower(), name=user.get_full_name() or user.email)
    customer.user = user
    customer.save()
    return customer


def attach_existing_login(customer: Customer) -> bool:
    """Link a staff-created customer to an existing portal login with the same email."""
    if customer.user_id:
        return False
    user = User.objects.filter(email=customer.email, role=Role.CUSTOMER, customer_profile__isnull=True).first()
    if user is None:
        return False
    customer.user = user
    customer.save(update_fields=["user", "updated_at"])
    return True
