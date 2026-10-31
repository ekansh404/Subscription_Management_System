from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests import make_user
from billing import services as billing
from billing.models import InvoiceStatus
from billing.tests import BillingFixtures

from .models import Payment
from .services import PaymentError, record_payment


class PaymentServiceTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()

    def setUp(self):
        self.invoice = billing.create_invoice(self.make_active())  # total 2124.00

    def test_draft_invoice_cannot_be_paid(self):
        with self.assertRaisesMessage(PaymentError, "Confirm the invoice"):
            record_payment(self.invoice, "100", method="upi")

    def test_partial_then_full_payment_marks_paid(self):
        billing.confirm_invoice(self.invoice)
        record_payment(self.invoice, "1000", method="upi", payment_date=date(2026, 8, 5), note="first half")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_due, Decimal("1124.00"))
        self.assertEqual(self.invoice.status, InvoiceStatus.CONFIRMED)
        payment = record_payment(self.invoice, "1124", method="bank_transfer", payment_date=date(2026, 8, 10))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.PAID)
        self.assertTrue(payment.number.startswith("PAY/2026/"))
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 2)

    def test_overpayment_and_future_dates_refused(self):
        billing.confirm_invoice(self.invoice)
        with self.assertRaisesMessage(PaymentError, "exceeds"):
            record_payment(self.invoice, "2124.01", method="cash")
        with self.assertRaisesMessage(PaymentError, "future"):
            record_payment(self.invoice, "1", method="cash", payment_date=timezone.localdate() + timedelta(days=1))

    def test_overdue_state(self):
        billing.confirm_invoice(self.invoice)
        self.assertTrue(self.invoice.is_overdue)  # due 16 Aug 2026
        self.assertEqual(self.invoice.payment_state, "overdue")
        record_payment(self.invoice, "2124", method="cash")
        self.invoice.refresh_from_db()
        self.assertFalse(self.invoice.is_overdue)
        self.assertEqual(self.invoice.payment_state, "paid")


class PaymentViewTests(BillingFixtures, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.make_catalog()
        cls.staff = make_user("staff@example.com", role=Role.STAFF)

    def test_register_payment_and_receivables(self):
        invoice = billing.create_invoice(self.make_active())
        billing.confirm_invoice(invoice)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("payments:receivables")), invoice.number)
        url = reverse("payments:payment_create", args=[invoice.pk])
        response = self.client.post(url, {"amount": "5000", "method": "upi", "payment_date": date.today().isoformat()})
        self.assertContains(response, "Cannot exceed the amount due")
        response = self.client.post(url, {"amount": "2124", "method": "upi", "payment_date": date.today().isoformat(), "reference": "UPI-1"})
        self.assertRedirects(response, invoice.get_absolute_url())
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.PAID)
        payment = Payment.objects.get()
        self.assertContains(self.client.get(reverse("payments:payment_list"), {"method": "upi"}), payment.number)
        self.assertContains(self.client.get(payment.get_absolute_url()), "Payment receipt")
