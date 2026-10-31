from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.tests import make_user
from billing import services as billing
from billing.tests import BillingFixtures
from customers.models import Customer
from subscriptions import services as subs
from subscriptions.models import Status


class PortalTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.user = make_user("acme@example.com")  # links to the Acme customer by email
        cls.other = Customer.objects.create(name="Other Co", email="other@example.com")

    def setUp(self):
        self.client.force_login(self.user)

    def test_home_redirect_and_dashboard(self):
        sub = self.make_active(start=date.today())
        invoice = billing.create_invoice(sub)
        billing.confirm_invoice(invoice)
        response = self.client.get(reverse("core:home"))
        self.assertRedirects(response, reverse("portal:home"))
        page = self.client.get(reverse("portal:home"))
        self.assertContains(page, sub.number)
        self.assertContains(page, invoice.number)

    def test_customer_sees_only_own_records(self):
        mine = self.make_active(start=date.today())
        theirs = subs.create_subscription(self.other, self.plan, start_date=date.today())
        subs.confirm(theirs)
        their_invoice = billing.create_invoice(theirs)
        billing.confirm_invoice(their_invoice)
        self.assertEqual(self.client.get(reverse("portal:subscription_detail", args=[mine.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("portal:subscription_detail", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("portal:invoice_detail", args=[their_invoice.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("portal:invoice_print", args=[their_invoice.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("portal:invoice_list")), their_invoice.number)
        response = self.client.post(reverse("portal:subscription_action", args=[theirs.pk, "pause"]))
        self.assertEqual(response.status_code, 404)

    def test_drafts_hidden_from_customer(self):
        draft = subs.create_subscription(self.customer, self.plan, start_date=date.today())
        self.assertEqual(self.client.get(reverse("portal:subscription_detail", args=[draft.pk])).status_code, 404)
        invoice = billing.create_invoice(self.make_active(start=date.today()))  # still a draft invoice
        self.assertEqual(self.client.get(reverse("portal:invoice_detail", args=[invoice.pk])).status_code, 404)

    def test_accept_quotation_then_pause_and_cancel_follow_plan_rules(self):
        sub = subs.create_subscription(self.customer, self.plan, start_date=date.today())
        subs.send_quotation(sub)
        self.client.post(reverse("portal:subscription_action", args=[sub.pk, "accept"]))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.ACTIVE)
        self.client.post(reverse("portal:subscription_action", args=[sub.pk, "pause"]))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.PAUSED)
        self.plan.closable = False
        self.plan.save()
        response = self.client.post(reverse("portal:subscription_action", args=[sub.pk, "close"]), follow=True)
        self.assertContains(response, "not available")
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.PAUSED)

    def test_staff_pages_forbidden_for_customers(self):
        for name in ("customers:list", "billing:invoice_list", "payments:payment_list", "subscriptions:subscription_list"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_customer_without_record_gets_one(self):
        Customer.objects.filter(user=self.user).update(user=None)
        self.assertEqual(self.client.get(reverse("portal:home")).status_code, 200)
        self.assertEqual(Customer.objects.filter(user=self.user).count(), 1)
