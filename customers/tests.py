from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.tests import VALID_PASSWORD, make_user

from .models import Customer
from .services import customer_for_user


class PortalLinkingTests(TestCase):
    def test_signup_creates_customer_record(self):
        self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Asha",
                "last_name": "Rao",
                "email": "asha@example.com",
                "password1": VALID_PASSWORD,
                "password2": VALID_PASSWORD,
            },
        )
        customer = Customer.objects.get(email="asha@example.com")
        self.assertEqual(customer.name, "Asha Rao")
        self.assertEqual(customer.user.email, "asha@example.com")

    def test_signup_links_to_customer_created_by_staff(self):
        existing = Customer.objects.create(name="Asha Traders", email="asha@example.com")
        user = make_user("asha@example.com")
        existing.refresh_from_db()
        self.assertEqual(existing.user, user)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(customer_for_user(user), existing)

    def test_staff_users_get_no_customer_record(self):
        make_user("staff@example.com", role=Role.STAFF)
        self.assertFalse(Customer.objects.exists())


class CustomerViewTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff@example.com", role=Role.STAFF)
        self.customer_user = make_user("buyer@example.com")
        Customer.objects.create(name="Zen Retail", email="zen@example.com", city="Lucknow")

    def test_staff_can_list_search_and_filter(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("customers:list"), {"q": "zen"})
        self.assertContains(response, "Zen Retail")
        self.assertNotContains(response, "buyer@example.com")
        response = self.client.get(reverse("customers:list"), {"portal": "yes"})
        self.assertContains(response, "buyer@example.com")
        self.assertNotContains(response, "Zen Retail")

    def test_staff_can_create_and_edit(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("customers:create"),
            {"name": "Nova Labs", "email": "Billing@Nova.io", "country": "India", "is_active": "on"},
        )
        customer = Customer.objects.get(email="billing@nova.io")
        self.assertRedirects(response, customer.get_absolute_url())
        response = self.client.post(
            reverse("customers:update", args=[customer.pk]),
            {"name": "Nova Labs Pvt", "email": "billing@nova.io", "country": "India"},
        )
        customer.refresh_from_db()
        self.assertEqual(customer.name, "Nova Labs Pvt")
        self.assertFalse(customer.is_active)

    def test_duplicate_email_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("customers:create"), {"name": "Copy", "email": "ZEN@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.filter(email="zen@example.com").count(), 1)

    def test_customers_and_anonymous_are_kept_out(self):
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(reverse("customers:list")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("customers:list")).status_code, 302)
