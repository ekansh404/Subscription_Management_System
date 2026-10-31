from datetime import date
from decimal import Decimal

from django.core import mail
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.tests import make_user
from catalog.models import Product
from catalog.services import generate_variants
from subscriptions import services as subs
from subscriptions.models import Status
from subscriptions.tests import Fixtures

from . import services
from .models import Discount, Invoice, InvoiceStatus

START = date(2026, 8, 1)


class BillingFixtures(Fixtures):
    @classmethod
    def make_active(cls, start=START, **kwargs):
        sub = subs.create_subscription(cls.customer, cls.plan, start_date=start, **kwargs)  # 2 x 900 + 18% GST
        subs.confirm(sub, today=start)
        return sub


class InvoiceGenerationTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()

    def test_invoice_snapshot_lines_taxes_and_totals(self):
        sub = self.make_active()
        invoice = services.create_invoice(sub)
        self.assertTrue(invoice.number.startswith("INV/2026/"))
        self.assertEqual(invoice.status, InvoiceStatus.DRAFT)
        self.assertEqual((invoice.period_start, invoice.period_end), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(invoice.due_date, date(2026, 8, 16))  # 15-day payment terms
        self.assertEqual(invoice.customer_name, "Acme")
        self.assertEqual(invoice.amount_untaxed, Decimal("1800.00"))
        self.assertEqual(invoice.amount_tax, Decimal("324.00"))
        self.assertEqual(invoice.amount_total, Decimal("2124.00"))
        self.assertEqual(invoice.lines.get().tax_label, "GST 18%")
        sub.refresh_from_db()
        self.assertEqual(sub.next_invoice_date, date(2026, 9, 1))

    def test_billing_run_catches_up_and_is_idempotent(self):
        self.make_active()
        first = services.run_billing(date(2026, 10, 31))
        self.assertEqual(len(first.invoices), 3)  # Aug, Sep, Oct: nothing skipped
        second = services.run_billing(date(2026, 10, 31))
        self.assertEqual(len(second.invoices), 0)  # nothing billed twice
        self.assertEqual(Invoice.objects.count(), 3)

    def test_database_forbids_a_second_invoice_for_the_same_period(self):
        sub = self.make_active()
        invoice = services.create_invoice(sub)
        with self.assertRaises(services.BillingError):
            services.create_invoice(sub, period_start=START)
        with self.assertRaises(IntegrityError):
            Invoice.objects.create(
                number="X", customer=self.customer, subscription=sub, invoice_date=START, due_date=START,
                period_start=invoice.period_start, customer_name="x", customer_email="x@example.com",
            )

    def test_paused_and_closed_subscriptions_are_not_billed(self):
        sub = self.make_active()
        subs.pause(sub)
        self.assertEqual(len(services.run_billing(date(2026, 9, 15)).invoices), 0)
        subs.resume(sub, today=date(2026, 9, 15))
        result = services.run_billing(date(2026, 9, 15))
        self.assertEqual([i.period_start for i in result.invoices], [date(2026, 9, 15)])

    def test_billing_stops_at_expiry_and_closes(self):
        self.make_active(expiry_date=date(2026, 9, 15))
        result = services.run_billing(date(2026, 10, 31))
        self.assertEqual(len(result.invoices), 2)
        self.assertEqual(result.invoices[-1].period_end, date(2026, 9, 15))
        self.assertEqual(result.closed, 1)

    def test_run_activates_future_subscriptions_on_their_start_date(self):
        sub = subs.create_subscription(self.customer, self.plan, start_date=date(2026, 9, 1))
        subs.confirm(sub, today=START)
        result = services.run_billing(date(2026, 9, 1))
        self.assertEqual(result.activated, 1)
        self.assertEqual(len(result.invoices), 1)

    def test_cancel_reopens_latest_period(self):
        sub = self.make_active()
        invoice = services.create_invoice(sub)
        services.cancel_invoice(invoice)
        sub.refresh_from_db()
        self.assertEqual(sub.next_invoice_date, START)
        again = services.create_invoice(sub)
        self.assertEqual(again.period_start, START)

    def test_workflow_confirm_send_and_guards(self):
        invoice = services.create_invoice(self.make_active())
        services.send_invoice(invoice)
        self.assertEqual(invoice.status, InvoiceStatus.CONFIRMED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(invoice.number, mail.outbox[0].subject)
        with self.assertRaises(services.BillingError):
            services.confirm_invoice(invoice)
        invoice.amount_paid = Decimal("1")
        with self.assertRaises(services.BillingError):
            services.cancel_invoice(invoice)


class DiscountTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        addon = Product.objects.create(name="Backup add-on", sales_price=Decimal("500"))
        cls.addon = generate_variants(addon)[0]

    def attach(self, sub, **fields):
        fields.setdefault("code", f"D{Discount.objects.count()}")
        fields.setdefault("name", "Promo")
        discount = Discount.objects.create(**fields)
        discount.subscriptions.add(sub)
        return discount

    def test_percentage_applies_before_tax_and_counts_usage(self):
        sub = self.make_active()
        discount = self.attach(sub, discount_type="percent", value=Decimal("10"))
        invoice = services.create_invoice(sub)
        self.assertEqual(invoice.amount_discount, Decimal("180.00"))
        self.assertEqual(invoice.amount_untaxed, Decimal("1620.00"))
        self.assertEqual(invoice.amount_tax, Decimal("291.60"))
        discount.refresh_from_db()
        self.assertEqual(discount.used_count, 1)

    def test_minimum_quantity_and_purchase(self):
        sub = self.make_active()  # 2 seats, 1800
        self.attach(sub, discount_type="percent", value=Decimal("10"), min_quantity=Decimal("10"))
        self.attach(sub, discount_type="fixed", value=Decimal("100"), min_purchase=Decimal("5000"))
        self.assertEqual(services.create_invoice(sub).amount_discount, Decimal("0.00"))

    def test_product_scope_only_discounts_matching_lines(self):
        sub = subs.create_subscription(self.customer, self.plan, start_date=START)
        subs.add_line(sub, self.addon, 1)
        subs.recompute_totals(sub)
        subs.confirm(sub, today=START)
        discount = self.attach(sub, discount_type="fixed", value=Decimal("200"), scope="products")
        discount.products.add(self.addon.product)
        invoice = services.create_invoice(sub)
        addon_line = invoice.lines.get(variant=self.addon)
        self.assertEqual(addon_line.discount_amount, Decimal("200.00"))
        self.assertEqual(invoice.amount_discount, Decimal("200.00"))

    def test_stops_when_usage_limit_reached_or_expired(self):
        sub = self.make_active()
        self.attach(sub, discount_type="fixed", value=Decimal("50"), usage_limit=1)
        self.attach(sub, discount_type="fixed", value=Decimal("30"), end_date=date(2026, 8, 31))
        result = services.run_billing(date(2026, 9, 30))
        august, september = result.invoices
        self.assertEqual(august.amount_discount, Decimal("80.00"))
        self.assertEqual(september.amount_discount, Decimal("0.00"))

    def test_fixed_discount_never_exceeds_lines(self):
        sub = self.make_active()
        self.attach(sub, discount_type="fixed", value=Decimal("99999"))
        invoice = services.create_invoice(sub)
        self.assertEqual(invoice.amount_untaxed, Decimal("0.00"))
        self.assertEqual(invoice.amount_total, Decimal("0.00"))


class BillingViewTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.admin = make_user("admin@example.com", role=Role.ADMIN)
        cls.staff = make_user("staff@example.com", role=Role.STAFF)

    def test_billing_run_page_and_invoice_pages(self):
        self.make_active(start=date.today())
        self.client.force_login(self.staff)
        response = self.client.post(reverse("billing:run"), {"run_date": date.today().isoformat(), "auto_confirm": "on"})
        self.assertContains(response, "1 invoice(s) created")
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.status, InvoiceStatus.CONFIRMED)
        self.assertContains(self.client.get(invoice.get_absolute_url()), invoice.number)
        self.client.post(reverse("billing:invoice_action", args=[invoice.pk, "send"]))
        self.assertIn(reverse("portal:invoice_detail", args=[invoice.pk]), mail.outbox[-1].body)  # customer-facing link
        self.assertContains(self.client.get(reverse("billing:invoice_print", args=[invoice.pk])), "Amount due")
        self.assertContains(self.client.get(reverse("billing:invoice_list"), {"state": "due"}), invoice.number)
        response = self.client.post(reverse("billing:run"), {"run_date": date.today().isoformat()})
        self.assertContains(response, "nothing was due")

    def test_only_admin_manages_discount_rules_staff_attaches(self):
        sub = self.make_active(start=date.today())
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("billing:discount_create")).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("billing:discount_create"),
            {"name": "Seats 10", "code": "seats10", "discount_type": "percent", "value": "10", "scope": "subscription",
             "min_purchase": "0", "min_quantity": "0", "is_active": "on"},
        )
        discount = Discount.objects.get(code="SEATS10")
        self.client.force_login(self.staff)
        self.client.post(reverse("billing:subscription_discount", args=[sub.pk]), {"discount": discount.pk})
        self.assertIn(sub, discount.subscriptions.all())
        self.client.post(reverse("billing:subscription_invoice", args=[sub.pk]))
        self.assertEqual(Invoice.objects.get().amount_discount, Decimal("180.00"))
        self.assertEqual(sub.status, Status.ACTIVE)


class SafeRedirectTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)

    def test_next_cannot_point_to_another_site(self):
        invoice = services.create_invoice(self.make_active())
        self.client.force_login(self.staff)
        url = reverse("billing:invoice_action", args=[invoice.pk, "confirm"])
        response = self.client.post(url, {"next": "https://evil.example.com/"})
        self.assertRedirects(response, invoice.get_absolute_url(), fetch_redirect_response=False)
        response = self.client.post(reverse("billing:invoice_action", args=[invoice.pk, "send"]), {"next": "/billing/invoices/"})
        self.assertRedirects(response, "/billing/invoices/", fetch_redirect_response=False)


class FailingEmailBackend:
    """Email backend that behaves like an unreachable SMTP server."""

    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise ConnectionRefusedError("SMTP server unreachable")


@override_settings(EMAIL_BACKEND="billing.tests.FailingEmailBackend")
class EmailFailureTests(BillingFixtures, TestCase):
    """A broken mail server shows a message; it never crashes a page."""

    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)

    def setUp(self):
        self.client.force_login(self.staff)
        self.invoice = services.create_invoice(self.make_active())
        services.confirm_invoice(self.invoice)

    def test_send_invoice_reports_error(self):
        with self.assertLogs("billing.services", "ERROR"):
            response = self.client.post(reverse("billing:invoice_action", args=[self.invoice.pk, "send"]), follow=True)
        self.assertContains(response, "could not be sent")
        self.invoice.refresh_from_db()
        self.assertIsNone(self.invoice.sent_at)

    def test_overdue_reminder_reports_error(self):
        with self.assertLogs("payments.views", "ERROR"):
            response = self.client.post(reverse("payments:payment_remind", args=[self.invoice.pk]), follow=True)
        self.assertContains(response, "could not be sent")

    def test_password_reset_still_shows_done_page(self):
        self.client.logout()
        make_user("someone@example.com")
        with self.assertLogs("django.contrib.auth", "ERROR"):  # Django logs and swallows mail errors here
            response = self.client.post(reverse("accounts:password_reset"), {"email": "someone@example.com"})
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
