from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.tests import make_user
from catalog.models import Plan, Product, Tax
from catalog.services import generate_variants
from customers.models import Customer

from . import services
from .models import QuotationTemplate, QuotationTemplateLine, Status, Subscription

TODAY = date(2026, 10, 31)


class Fixtures:
    """Shared catalog: GST 18%, a seat product at 1000 and a monthly plan (min 2 seats)."""

    @classmethod
    def make_catalog(cls):
        cls.gst = Tax.objects.create(name="GST", rate=Decimal("18"))
        cls.product = Product.objects.create(name="Seat", sales_price=Decimal("1000"))
        cls.product.taxes.add(cls.gst)
        cls.variant = generate_variants(cls.product)[0]
        cls.plan = Plan.objects.create(
            name="Team Monthly", product=cls.variant, price=Decimal("900"), min_quantity=2, pausable=True
        )
        cls.customer = Customer.objects.create(name="Acme", email="acme@example.com")


class LifecycleTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()

    def new(self, **kwargs):
        kwargs.setdefault("start_date", TODAY)
        return services.create_subscription(self.customer, self.plan, **kwargs)

    def test_plan_line_totals_and_number(self):
        sub = self.new()
        self.assertTrue(sub.number.startswith("SUB-"))
        self.assertEqual(sub.lines.count(), 1)
        self.assertEqual(sub.amount_untaxed, Decimal("1800.00"))  # 2 x 900
        self.assertEqual(sub.amount_tax, Decimal("324.00"))
        self.assertEqual(sub.amount_total, Decimal("2124.00"))
        self.assertEqual(sub.mrr, Decimal("1800.00"))

    def test_full_happy_path(self):
        sub = self.new()
        services.send_quotation(sub, today=TODAY)
        self.assertEqual(sub.status, Status.QUOTATION)
        self.assertEqual(sub.quotation_valid_until, TODAY + timedelta(days=30))
        services.confirm(sub, today=TODAY)
        self.assertEqual(sub.status, Status.ACTIVE)  # start date reached -> active immediately
        self.assertEqual(sub.next_invoice_date, TODAY)
        services.pause(sub)
        services.resume(sub, today=TODAY + timedelta(days=3))
        self.assertEqual(sub.next_invoice_date, TODAY + timedelta(days=3))
        services.close(sub, today=TODAY + timedelta(days=5))
        self.assertEqual(sub.status, Status.CLOSED)
        self.assertEqual(sub.events.count(), 7)

    def test_future_start_stays_confirmed_until_activated(self):
        sub = self.new(start_date=TODAY + timedelta(days=10))
        services.confirm(sub, today=TODAY)
        self.assertEqual(sub.status, Status.CONFIRMED)
        self.assertEqual(services.activate_due(TODAY), 0)
        self.assertEqual(services.activate_due(TODAY + timedelta(days=10)), 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.ACTIVE)

    def test_minimum_quantity_enforced(self):
        sub = self.new()
        sub.lines.update(quantity=1)
        with self.assertRaisesMessage(services.TransitionError, "minimum quantity of 2"):
            services.confirm(sub, today=TODAY)

    def test_expired_quotation_cannot_be_confirmed(self):
        sub = self.new()
        services.send_quotation(sub, today=TODAY)
        with self.assertRaisesMessage(services.TransitionError, "expired"):
            services.confirm(sub, today=TODAY + timedelta(days=31))

    def test_plan_availability_window(self):
        self.plan.end_date = TODAY - timedelta(days=1)
        self.plan.save()
        sub = self.new()
        with self.assertRaisesMessage(services.TransitionError, "not available"):
            services.confirm(sub, today=TODAY)

    def test_plan_rules_block_pause_and_close(self):
        plan = Plan.objects.create(name="Locked", product=self.variant, price=Decimal("10"), pausable=False, closable=False)
        sub = services.create_subscription(self.customer, plan, start_date=TODAY)
        services.confirm(sub, today=TODAY)
        self.assertNotIn("pause", services.available_actions(sub, TODAY))
        with self.assertRaises(services.TransitionError):
            services.pause(sub)
        with self.assertRaises(services.TransitionError):
            services.close(sub)

    def test_auto_close_at_expiry_and_renew(self):
        sub = self.new(expiry_date=TODAY + timedelta(days=29))
        services.confirm(sub, today=TODAY)
        self.assertEqual(services.close_expired(TODAY + timedelta(days=29)), 0)
        self.assertEqual(services.close_expired(TODAY + timedelta(days=30)), 1)
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.CLOSED)
        services.renew(sub, today=TODAY + timedelta(days=31))
        self.assertEqual(sub.status, Status.ACTIVE)
        # Renewed after lapsing: a fresh 30-day term starting on the renewal day.
        self.assertEqual(sub.expiry_date, TODAY + timedelta(days=60))

    def test_from_template_copies_lines_terms_and_length(self):
        template = QuotationTemplate.objects.create(
            name="Enterprise 12m", plan=self.plan, validity_days=15, duration_periods=12, payment_term_days=30
        )
        QuotationTemplateLine.objects.create(template=template, variant=self.variant, quantity=10, unit_price=Decimal("850"))
        sub = services.create_subscription(self.customer, self.plan, start_date=TODAY, template=template)
        self.assertEqual(sub.payment_term_days, 30)
        self.assertEqual(sub.expiry_date, date(2027, 10, 30))
        self.assertEqual(sub.amount_untaxed, Decimal("8500.00"))
        services.send_quotation(sub, today=TODAY)
        self.assertEqual(sub.quotation_valid_until, TODAY + timedelta(days=15))


class SubscriptionViewTests(Fixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)
        cls.customer_user = make_user("buyer@example.com")

    def setUp(self):
        self.client.force_login(self.staff)

    def formset(self, prefix="lines", rows=()):
        data = {f"{prefix}-TOTAL_FORMS": str(len(rows)), f"{prefix}-INITIAL_FORMS": "0", f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000"}
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"{prefix}-{index}-{key}"] = value
        return data

    def test_create_with_lines_then_confirm_via_buttons(self):
        today = date.today()
        data = {
            "customer": self.customer.pk,
            "plan": self.plan.pk,
            "start_date": today.isoformat(),
            "payment_term_days": "15",
            **self.formset(rows=[{"variant": self.variant.pk, "quantity": "3", "unit_price": "1000", "taxes": [self.gst.pk]}]),
        }
        response = self.client.post(reverse("subscriptions:subscription_create"), data)
        sub = Subscription.objects.get()
        self.assertRedirects(response, sub.get_absolute_url())
        self.assertEqual(sub.amount_total, Decimal("3540.00"))
        self.client.post(reverse("subscriptions:subscription_action", args=[sub.pk, "send"]))
        self.client.post(reverse("subscriptions:subscription_action", args=[sub.pk, "confirm"]))
        sub.refresh_from_db()
        self.assertEqual(sub.status, Status.ACTIVE)
        page = self.client.get(sub.get_absolute_url())
        self.assertContains(page, "Subscription confirmed.")
        self.assertEqual(self.client.get(reverse("subscriptions:subscription_update", args=[sub.pk])).status_code, 404)

    def test_invalid_dates_rejected(self):
        today = date.today()
        data = {
            "customer": self.customer.pk,
            "plan": self.plan.pk,
            "start_date": today.isoformat(),
            "expiry_date": (today - timedelta(days=1)).isoformat(),
            "payment_term_days": "15",
            **self.formset(),
        }
        self.assertEqual(self.client.post(reverse("subscriptions:subscription_create"), data).status_code, 200)
        self.assertFalse(Subscription.objects.exists())

    def test_disallowed_action_shows_error(self):
        sub = services.create_subscription(self.customer, self.plan, start_date=date.today())
        response = self.client.post(reverse("subscriptions:subscription_action", args=[sub.pk, "pause"]), follow=True)
        self.assertContains(response, "Not possible while the subscription is draft")

    def test_list_filters_and_customer_blocked(self):
        services.create_subscription(self.customer, self.plan, start_date=date.today())
        response = self.client.get(reverse("subscriptions:subscription_list"), {"status": "draft"})
        self.assertContains(response, "SUB-")
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(reverse("subscriptions:subscription_list")).status_code, 403)
