from django.db import migrations


def link_existing_customers(apps, schema_editor):
    """Customer-role users created before this app existed get a customer record."""
    User = apps.get_model("accounts", "User")
    Customer = apps.get_model("customers", "Customer")
    for user in User.objects.filter(role="customer", customer_profile__isnull=True):
        customer = Customer.objects.filter(email=user.email.lower(), user__isnull=True).first()
        if customer is None:
            name = f"{user.first_name} {user.last_name}".strip() or user.email
            customer = Customer(email=user.email.lower(), name=name)
        customer.user = user
        customer.save()


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [migrations.RunPython(link_existing_customers, migrations.RunPython.noop)]
