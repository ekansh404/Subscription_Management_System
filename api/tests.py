from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.models import Role, User
from accounts.tests import make_user
from billing import services as billing
from billing.tests import BillingFixtures
from customers.models import Customer
from subscriptions import services as subs
from subscriptions.models import Subscription


class ApiTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)
        cls.customer_user = make_user("acme@example.com")
        mine = cls.make_active(start=date.today())
        other = Customer.objects.create(name="Other", email="other@example.com")
        theirs = subs.create_subscription(other, cls.plan, start_date=date.today())
        subs.confirm(theirs)
        for sub in (mine, theirs):
            billing.confirm_invoice(billing.create_invoice(sub))

    def test_staff_reads_everything(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/api/subscriptions/").json()["count"], 2)
        self.assertEqual(self.client.get("/api/invoices/").json()["count"], 2)
        self.assertEqual(self.client.get("/api/kpis/").json()["active_subscriptions"], 2)
        self.assertEqual(self.client.get("/api/customers/").status_code, 200)

    def test_customer_reads_only_own_and_no_staff_endpoints(self):
        self.client.force_login(self.customer_user)
        data = self.client.get("/api/subscriptions/").json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["customer"], "Acme")
        self.assertEqual(self.client.get("/api/invoices/").json()["count"], 1)
        self.assertEqual(self.client.get("/api/customers/").status_code, 403)
        self.assertEqual(self.client.get("/api/kpis/").status_code, 403)

    def test_read_only_and_login_required(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post("/api/subscriptions/", {}).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get("/api/subscriptions/").status_code, 403)


class SeedDemoTests(TestCase):
    def test_seed_demo_builds_consistent_data(self):
        call_command("seed_demo", customers=6, subscriptions=12, months_back=2, verbosity=0, stdout=StringIO())
        self.assertEqual(Customer.objects.count(), 6)
        self.assertEqual(Subscription.objects.count(), 12)
        self.assertTrue(User.objects.filter(email="admin@brightloop.com", role=Role.ADMIN).exists())
        self.assertEqual(len(billing.run_billing().invoices), 0)  # seeding already billed everything due
