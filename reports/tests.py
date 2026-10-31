from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.tests import make_user
from billing import services as billing
from billing.tests import BillingFixtures
from payments.services import record_payment

from . import services
from .services import ReportFilters


class ReportTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)
        sub = cls.make_active(start=date(2026, 8, 1))
        for invoice in billing.run_billing(date(2026, 10, 31), auto_confirm=True).invoices:  # Aug, Sep, Oct: 2124 each
            if invoice.period_start.month == 8:
                record_payment(invoice, invoice.amount_total, method="upi", payment_date=date(2026, 8, 10))
        cls.sub = sub

    def filters(self):
        return ReportFilters(date_from=date(2026, 8, 1), date_to=date(2026, 10, 31))

    def test_kpis(self):
        kpi = services.kpis(self.filters())
        self.assertEqual(kpi["subscriptions"]["active"], 1)
        self.assertEqual(kpi["subscriptions"]["mrr"], Decimal("1800.00"))
        self.assertEqual(kpi["billed"]["invoiced"], Decimal("6372.00"))
        self.assertEqual(kpi["collected"]["amount"], Decimal("2124.00"))
        self.assertEqual(kpi["outstanding"]["amount"], Decimal("4248.00"))
        self.assertEqual(kpi["outstanding"]["count"], 2)

    def test_monthly_series_includes_every_month(self):
        rows = services.monthly_series(self.filters())
        self.assertEqual([row["month"].month for row in rows], [8, 9, 10])
        self.assertEqual(rows[0]["collected"], Decimal("2124.00"))
        self.assertEqual(rows[1]["invoiced"], Decimal("2124.00"))

    def test_plan_filter(self):
        filters = self.filters()
        filters.plan_id = self.plan.pk + 999
        self.assertEqual(services.kpis(filters)["billed"]["invoiced"], Decimal("0"))

    def test_pages_and_csv(self):
        self.client.force_login(self.staff)
        params = {"date_from": "2026-08-01", "date_to": "2026-10-31"}
        self.assertContains(self.client.get(reverse("reports:dashboard"), params), "Monthly recurring revenue")
        self.assertContains(self.client.get(reverse("reports:revenue"), params), "August 2026")
        response = self.client.get(reverse("reports:revenue_csv"), params)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("2026-08,1,1800.00,0.00,324.00,2124.00,2124.00", response.content.decode())

    def test_staff_lands_on_dashboard(self):
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("core:home")), reverse("reports:dashboard"))
