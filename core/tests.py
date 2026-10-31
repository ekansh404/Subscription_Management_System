import io
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.sequences import next_number
from core.templatetags.core_tags import money, percent
from core.utils.dates import DAILY, MONTHLY, WEEKLY, YEARLY, add_months, add_period, monthly_amount, period_end


class SequenceTests(TestCase):
    def test_numbers_increment_per_key(self):
        self.assertEqual(next_number("sub", prefix="SUB"), "SUB-00001")
        self.assertEqual(next_number("sub", prefix="SUB"), "SUB-00002")
        self.assertEqual(next_number("inv-2026", prefix="INV/2026", separator="/"), "INV/2026/00001")


class DateMathTests(TestCase):
    def test_add_months_clamps_to_month_end(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(add_months(date(2026, 11, 15), 2), date(2027, 1, 15))

    def test_add_period(self):
        start = date(2026, 10, 31)
        self.assertEqual(add_period(start, DAILY), date(2026, 11, 1))
        self.assertEqual(add_period(start, WEEKLY), date(2026, 11, 7))
        self.assertEqual(add_period(start, MONTHLY), date(2026, 11, 30))
        self.assertEqual(add_period(start, YEARLY), date(2027, 10, 31))
        self.assertEqual(period_end(date(2026, 10, 1), MONTHLY), date(2026, 10, 31))

    def test_monthly_normalisation(self):
        self.assertEqual(monthly_amount(Decimal("1200"), YEARLY), Decimal("100.00"))
        self.assertEqual(monthly_amount(Decimal("10"), DAILY), Decimal("300.00"))


class TemplateFilterTests(TestCase):
    def test_money_and_percent(self):
        self.assertTrue(money(Decimal("1234.5")).endswith("1,234.50"))
        self.assertTrue(money(Decimal("-5")).startswith("-"))
        self.assertEqual(percent(Decimal("18.00")), "18%")
        self.assertEqual(percent(Decimal("12.50")), "12.5%")


class HomeViewTests(TestCase):
    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_healthcheck(self):
        response = self.client.get(reverse("core:healthcheck"))
        self.assertEqual(response.json(), {"status": "ok"})


class OutboxTests(TestCase):
    def test_outbox_backend_stores_and_admin_reads_emails(self):
        from django.core.mail import get_connection, send_mail

        from accounts.tests import make_user

        from .models import OutboxEmail

        with redirect_stdout(io.StringIO()):  # the outbox also prints to the terminal
            connection = get_connection("core.mail.OutboxEmailBackend")
            send_mail("Reset your password", "Open http://testserver/reset/abc/ to continue.", "billing@example.com",
                          ["asha@example.com"], connection=connection)
        email = OutboxEmail.objects.get()
        self.assertEqual(email.to, "asha@example.com")

        admin = make_user("admin@example.com", role="admin")
        staff = make_user("staff@example.com", role="staff")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("core:outbox")).status_code, 403)
        self.client.force_login(admin)
        self.assertContains(self.client.get(reverse("core:outbox")), "Reset your password")
        page = self.client.get(reverse("core:outbox_detail", args=[email.pk]))
        self.assertContains(page, '<a href="http://testserver/reset/abc/"', html=False)
