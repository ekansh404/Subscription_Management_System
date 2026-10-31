from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Role, User

from .services import link_portal_account


@receiver(post_save, sender=User)
def create_customer_for_portal_user(sender, instance, created, raw=False, **kwargs):
    """Every customer who signs up gets (or is linked to) a customer record."""
    if raw or not created or instance.role != Role.CUSTOMER:
        return
    link_portal_account(instance)
