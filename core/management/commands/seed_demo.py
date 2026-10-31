"""
Demo data for the video and for load testing.

    python manage.py seed_demo                      # 25 customers, 60 subscriptions, 6 months of history
    python manage.py seed_demo --reset --subscriptions 3000 --customers 400 --months-back 2

Everything goes through the real services (create_subscription, confirm,
run_billing, record_payment), so the demo data obeys the same rules as data
entered by hand. Random choices use a fixed seed: the same command always
produces the same data.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, User
from billing import services as billing
from billing.models import Discount, Invoice, InvoiceStatus
from catalog.models import AttributeValue, Plan, Product, ProductAttribute, Tax
from catalog.services import generate_variants
from core.models import Sequence
from core.utils.dates import add_months
from customers.models import Customer
from payments.models import Payment, PaymentMethod
from payments.services import record_payment
from subscriptions import services as subs
from subscriptions.models import QuotationTemplate, QuotationTemplateLine, Subscription

STAFF_USERS = [
    ("admin@brightloop.com", "Admin#12345", "Asha", "Verma", Role.ADMIN),
    ("staff@brightloop.com", "Staff#12345", "Rohan", "Mehta", Role.STAFF),
    ("finance@brightloop.com", "Finance#12345", "Neha", "Kapoor", Role.STAFF),
]
CUSTOMER_PASSWORD = "Customer#12345"
COMPANIES = [
    "Lucknow Textiles", "Gomti Foods", "Awadh Pharma", "Hazratganj Retail", "Chikan Crafts", "Nawab Logistics",
    "Kanpur Leatherworks", "Varanasi Silks", "Agra Marble Co", "Prayag Electronics", "Ganga Solar", "Doon Organics",
    "Indore Spices", "Jaipur Gems", "Bhopal Motors", "Patna Paper Mills", "Ranchi Steelworks", "Noida Softworks",
    "Gurgaon Analytics", "Delhi Design Studio", "Meerut Sports", "Aligarh Locks", "Bareilly Furniture", "Jhansi Agro",
    "Ayodhya Tours",
]
FIRST_NAMES = ["Aarav", "Diya", "Kabir", "Isha", "Vivaan", "Ananya", "Arjun", "Meera", "Reyansh", "Saanvi", "Aditya", "Kiara"]
LAST_NAMES = ["Sharma", "Gupta", "Singh", "Srivastava", "Mishra", "Agarwal", "Khan", "Tripathi", "Pandey", "Yadav"]
CITIES = ["Lucknow", "Kanpur", "Varanasi", "Prayagraj", "Agra", "Noida", "Delhi", "Jaipur", "Indore", "Patna"]


class Command(BaseCommand):
    help = "Create demo users, catalog, customers, subscriptions, invoices and payments."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing business data first (keeps your own logins).")
        parser.add_argument("--customers", type=int, default=25)
        parser.add_argument("--subscriptions", type=int, default=60)
        parser.add_argument("--months-back", type=int, default=6)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        self.rng = random.Random(options["seed"])
        self.today = timezone.localdate()
        if options["reset"]:
            self.reset()
        elif Subscription.objects.exists():
            self.stdout.write(self.style.WARNING("Data already exists. Run with --reset to rebuild the demo data."))
            return
        with transaction.atomic():
            self.create_users()
            self.create_catalog()
            customers = self.create_customers(options["customers"])
            self.create_subscriptions(customers, options["subscriptions"], options["months_back"])
        self.stdout.write("Running billing for every period up to today...")
        result = billing.run_billing(self.today, auto_confirm=True)
        self.stdout.write(f"  {len(result.invoices)} invoices created")
        self.create_payments()
        self.summary()

    # --- steps -----------------------------------------------------------------

    def reset(self):
        self.stdout.write("Deleting existing business data...")
        Payment.objects.all().delete()
        Invoice.objects.all().delete()
        Discount.objects.all().delete()
        Subscription.objects.all().delete()
        QuotationTemplate.objects.all().delete()
        Plan.objects.all().delete()
        Product.objects.all().delete()
        ProductAttribute.objects.all().delete()
        Tax.objects.all().delete()
        Customer.objects.all().delete()
        Sequence.objects.all().delete()
        demo_emails = [email for email, *_ in STAFF_USERS]
        User.objects.filter(email__in=demo_emails).delete()
        User.objects.filter(role=Role.CUSTOMER, email__endswith="@example.com").delete()

    def create_users(self):
        for email, password, first, last, role in STAFF_USERS:
            if User.objects.filter(email=email).exists():
                continue
            if role == Role.ADMIN:
                User.objects.create_superuser(email, password, first_name=first, last_name=last)
            else:
                User.objects.create_staff(email, password, first_name=first, last_name=last)
        self.salespeople = list(User.objects.filter(role__in=[Role.ADMIN, Role.STAFF]))

    def create_catalog(self):
        gst = Tax.objects.create(name="GST", rate=Decimal("18"), description="Goods and Services Tax")
        Tax.objects.create(name="GST (reduced)", rate=Decimal("5"), description="Reduced rate for training services")
        brand = ProductAttribute.objects.create(name="Brand")
        odoo = AttributeValue.objects.create(attribute=brand, name="Odoo", price_extra=Decimal("560"), sequence=1)
        generic = AttributeValue.objects.create(attribute=brand, name="Generic", sequence=2)
        edition = ProductAttribute.objects.create(name="Edition")
        cloud = AttributeValue.objects.create(attribute=edition, name="Cloud", sequence=1)
        onprem = AttributeValue.objects.create(attribute=edition, name="On-premise", price_extra=Decimal("1500"), sequence=2)

        def product(name, price, cost, kind="service", values=(), notes=""):
            item = Product.objects.create(name=name, product_type=kind, sales_price=Decimal(price), cost_price=Decimal(cost), notes=notes)
            item.taxes.add(gst)
            item.attribute_values.set(values)
            return generate_variants(item)

        crm = product("Brightloop CRM seat", "1200", "300", notes="Per-user licence for the CRM.")
        erp = product("ERP Connector", "2500", "800", values=[odoo, generic], notes="Sync with your ERP. Odoo brand adds 560.")
        helpdesk = product("Helpdesk", "900", "200", values=[cloud, onprem])
        backup = product("Cloud Backup add-on", "499", "120", kind="addon")
        analytics = product("Analytics add-on", "799", "150", kind="addon")
        support = product("Priority support", "3000", "1500", kind="addon")

        year_ago = self.today - timedelta(days=400)
        self.plans = [
            Plan.objects.create(name="Starter Monthly", product=crm[0], price=Decimal("999"), billing_period="monthly", min_quantity=1, pausable=True, start_date=year_ago, description="For small shops."),
            Plan.objects.create(name="Team Monthly", product=crm[0], price=Decimal("1099"), billing_period="monthly", min_quantity=5, pausable=True, start_date=year_ago, description="Five seats or more."),
            Plan.objects.create(name="Business Yearly", product=crm[0], price=Decimal("11000"), billing_period="yearly", min_quantity=10, closable=False, start_date=year_ago, description="Yearly contract; cannot be closed early."),
            Plan.objects.create(name="Connector Weekly", product=erp[0], price=Decimal("700"), billing_period="weekly", start_date=year_ago, auto_close=True),
            Plan.objects.create(name="Helpdesk Monthly", product=helpdesk[0], price=Decimal("900"), billing_period="monthly", min_quantity=2, start_date=year_ago),
        ]
        self.addons = backup + analytics + support + erp
        template = QuotationTemplate.objects.create(
            name="Enterprise bundle (12 months)", plan=self.plans[1], validity_days=15, duration_periods=12, payment_term_days=30,
            notes="Includes onboarding. Prices exclude GST.",
        )
        QuotationTemplateLine.objects.create(template=template, variant=crm[0], quantity=10, unit_price=Decimal("1050"))
        QuotationTemplateLine.objects.create(template=template, variant=analytics[0], quantity=1, unit_price=Decimal("799"))
        QuotationTemplateLine.objects.create(template=template, variant=support[0], quantity=1, unit_price=Decimal("2500"))
        QuotationTemplate.objects.create(name="Starter quick quote", plan=self.plans[0], validity_days=7, payment_term_days=15)
        self.templates = list(QuotationTemplate.objects.all())
        self.discounts = [
            Discount.objects.create(name="10 seats or more", code="SEATS10", discount_type="percent", value=Decimal("10"), min_quantity=Decimal("10")),
            Discount.objects.create(name="Launch offer", code="LAUNCH500", discount_type="fixed", value=Decimal("500"),
                                    start_date=add_months(self.today, -3), end_date=self.today + timedelta(days=30), usage_limit=40),
        ]

    def create_customers(self, count):
        customers = []
        for index in range(count):
            company = COMPANIES[index % len(COMPANIES)] + ("" if index < len(COMPANIES) else f" {index // len(COMPANIES) + 1}")
            first, last = self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)
            email = f"customer{index + 1}@example.com"
            customer = Customer.objects.create(
                name=f"{first} {last}", company=company, email=email, phone=f"+91 9{self.rng.randint(100000000, 999999999)}",
                city=self.rng.choice(CITIES), state="Uttar Pradesh", country="India", street=f"{self.rng.randint(1, 300)} MG Road",
                postal_code=f"2260{self.rng.randint(10, 99)}", tax_id=f"09AAAC{self.rng.randint(1000, 9999)}B1Z{self.rng.randint(1, 9)}",
            )
            if index < 10:  # the first ten can sign in to the portal (linked by email)
                User.objects.create_user(email, CUSTOMER_PASSWORD, first_name=first, last_name=last)
            customers.append(customer)
        return customers

    def create_subscriptions(self, customers, count, months_back):
        earliest = add_months(self.today, -months_back)
        span = (self.today - earliest).days
        for index in range(count):
            customer = customers[index % len(customers)] if index < len(customers) else self.rng.choice(customers)
            plan = self.rng.choices(self.plans, weights=[30, 30, 10, 10, 20])[0]
            start = earliest + timedelta(days=self.rng.randint(0, max(span - 1, 0)))
            roll = self.rng.random()
            if roll < 0.08:  # open quotations and drafts
                sub = subs.create_subscription(customer, plan, start_date=self.today + timedelta(days=self.rng.randint(0, 20)),
                                               user=self.rng.choice(self.salespeople))
                if roll < 0.05:
                    subs.send_quotation(sub, today=self.today)
                continue
            template = self.templates[0] if plan == self.templates[0].plan and self.rng.random() < 0.4 else None
            sub = subs.create_subscription(customer, plan, start_date=start, template=template, user=self.rng.choice(self.salespeople))
            line = sub.lines.first()
            if line and line.quantity < plan.min_quantity + 3:
                line.quantity = plan.min_quantity + self.rng.randint(0, 12)
                line.save()
            if self.rng.random() < 0.35:
                subs.add_line(sub, self.rng.choice(self.addons), self.rng.randint(1, 3))
            subs.recompute_totals(sub)
            if self.rng.random() < 0.25:
                self.rng.choice(self.discounts).subscriptions.add(sub)
            subs.send_quotation(sub, today=start - timedelta(days=3))
            subs.confirm(sub, today=start)
            if self.rng.random() < 0.08 and plan.pausable:
                subs.pause(sub)
            elif self.rng.random() < 0.08 and plan.closable:
                billing.bill_subscription(sub, today=self.today)
                subs.close(sub, reason="Moved to a different provider", today=self.today)

    def create_payments(self):
        """Most invoices are paid on time, some late, some partially, some not at all (overdue)."""
        methods = [choice for choice, _ in PaymentMethod.choices]
        open_invoices = Invoice.objects.filter(status=InvoiceStatus.CONFIRMED).order_by("invoice_date")
        for invoice in open_invoices.iterator():
            roll = self.rng.random()
            age = (self.today - invoice.invoice_date).days
            if roll < 0.12 or (age < 10 and roll < 0.6):
                continue  # unpaid: becomes overdue once its due date passes
            pay_date = min(invoice.invoice_date + timedelta(days=self.rng.randint(1, 25)), self.today)
            amount = invoice.amount_due
            if roll < 0.2:
                amount = (amount / 2).quantize(Decimal("0.01"))
            record_payment(invoice, amount, method=self.rng.choice(methods), payment_date=pay_date,
                           reference=f"TXN{self.rng.randint(100000, 999999)}")

    def summary(self):
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {Customer.objects.count()} customers, {Subscription.objects.count()} subscriptions, "
            f"{Invoice.objects.count()} invoices, {Payment.objects.count()} payments."
        ))
        self.stdout.write("Logins:")
        for email, password, *_ in STAFF_USERS:
            self.stdout.write(f"  {email} / {password}")
        self.stdout.write(f"  customer1@example.com … customer10@example.com / {CUSTOMER_PASSWORD}")
