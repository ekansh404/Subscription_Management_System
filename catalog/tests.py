from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.tests import make_user

from .models import AttributeValue, Plan, Product, ProductAttribute, Tax
from .services import generate_variants


def make_brand_attribute():
    brand = ProductAttribute.objects.create(name="Brand")
    odoo = AttributeValue.objects.create(attribute=brand, name="Odoo", price_extra=Decimal("560"))
    generic = AttributeValue.objects.create(attribute=brand, name="Generic")
    return brand, odoo, generic


class VariantGenerationTests(TestCase):
    def test_product_without_attributes_gets_one_variant(self):
        product = Product.objects.create(name="CRM Suite", sales_price=Decimal("1000"))
        variants = generate_variants(product)
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0].price, Decimal("1000"))

    def test_brand_odoo_adds_560(self):
        _, odoo, generic = make_brand_attribute()
        product = Product.objects.create(name="ERP Connector", sales_price=Decimal("1000"))
        product.attribute_values.set([odoo, generic])
        prices = {variant.name: variant.price for variant in generate_variants(product)}
        self.assertEqual(prices["ERP Connector (Odoo)"], Decimal("1560"))
        self.assertEqual(prices["ERP Connector (Generic)"], Decimal("1000"))

    def test_combinations_and_regeneration_archives_dropped_values(self):
        _, odoo, generic = make_brand_attribute()
        edition = ProductAttribute.objects.create(name="Edition")
        cloud = AttributeValue.objects.create(attribute=edition, name="Cloud", price_extra=Decimal("100"))
        onprem = AttributeValue.objects.create(attribute=edition, name="On-prem")
        product = Product.objects.create(name="Suite", sales_price=Decimal("500"))
        product.attribute_values.set([odoo, generic, cloud, onprem])
        self.assertEqual(len(generate_variants(product)), 4)
        product.attribute_values.set([odoo, cloud, onprem])
        active = generate_variants(product)
        self.assertEqual(len(active), 2)
        self.assertEqual(product.variants.filter(is_active=False).count(), 2)
        self.assertIn(Decimal("1160"), [variant.price for variant in active])


class PlanTests(TestCase):
    def test_availability_window(self):
        today = date.today()
        plan = Plan.objects.create(
            name="Launch", price=Decimal("999"), start_date=today, end_date=today + timedelta(days=30)
        )
        self.assertTrue(plan.is_available(today))
        self.assertFalse(plan.is_available(today - timedelta(days=1)))
        self.assertFalse(plan.is_available(today + timedelta(days=31)))
        plan.is_active = False
        self.assertFalse(plan.is_available(today))

    def test_monthly_price_normalisation(self):
        plan = Plan(name="Yearly", price=Decimal("12000"), billing_period="yearly")
        self.assertEqual(plan.monthly_price, Decimal("1000.00"))


class CatalogViewTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", role=Role.ADMIN)
        self.staff = make_user("staff@example.com", role=Role.STAFF)
        self.gst = Tax.objects.create(name="GST", rate=Decimal("18"))

    def test_admin_creates_product_with_variants(self):
        _, odoo, generic = make_brand_attribute()
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("catalog:product_create"),
            {
                "name": "Helpdesk",
                "product_type": "service",
                "sales_price": "1000",
                "cost_price": "200",
                "taxes": [self.gst.pk],
                "attribute_values": [odoo.pk, generic.pk],
                "is_active": "on",
            },
        )
        product = Product.objects.get(name="Helpdesk")
        self.assertRedirects(response, product.get_absolute_url())
        self.assertEqual(product.variants.count(), 2)
        self.assertContains(self.client.get(product.get_absolute_url()), "Helpdesk (Odoo)")

    def test_admin_creates_plan_and_dates_are_validated(self):
        self.client.force_login(self.admin)
        data = {"name": "Pro Monthly", "price": "999", "billing_period": "monthly", "min_quantity": "1"}
        bad = {**data, "start_date": "2026-12-01", "end_date": "2026-11-01"}
        self.assertEqual(self.client.post(reverse("catalog:plan_create"), bad).status_code, 200)
        self.assertFalse(Plan.objects.exists())
        self.client.post(reverse("catalog:plan_create"), {**data, "pausable": "on"})
        self.assertTrue(Plan.objects.get(name="Pro Monthly").pausable)

    def test_attribute_with_values_formset(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("catalog:attribute_create"),
            {
                "name": "Brand",
                "values-TOTAL_FORMS": "2",
                "values-INITIAL_FORMS": "0",
                "values-MIN_NUM_FORMS": "1",
                "values-MAX_NUM_FORMS": "1000",
                "values-0-name": "Odoo",
                "values-0-price_extra": "560",
                "values-0-sequence": "10",
                "values-1-name": "Generic",
                "values-1-price_extra": "0",
                "values-1-sequence": "20",
            },
        )
        self.assertRedirects(response, reverse("catalog:attribute_list"))
        self.assertEqual(AttributeValue.objects.get(name="Odoo").price_extra, Decimal("560"))

    def test_staff_can_view_but_not_edit(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("catalog:product_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalog:plan_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalog:product_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("catalog:plan_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("catalog:tax_list")).status_code, 403)
