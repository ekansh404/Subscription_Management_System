from rest_framework import serializers

from billing.models import Invoice, InvoiceLine
from catalog.models import Plan, Product, ProductVariant
from customers.models import Customer
from payments.models import Payment
from subscriptions.models import Subscription, SubscriptionLine


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "company", "email", "phone", "city", "country", "tax_id", "is_active", "created_at"]


class VariantSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ProductVariant
        fields = ["id", "name", "price_extra", "price", "is_active"]


class ProductSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True, read_only=True)
    taxes = serializers.StringRelatedField(many=True)

    class Meta:
        model = Product
        fields = ["id", "name", "product_type", "sales_price", "cost_price", "taxes", "is_active", "variants"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id", "name", "price", "billing_period", "min_quantity", "start_date", "end_date",
            "auto_close", "closable", "pausable", "renewable", "is_active",
        ]


class SubscriptionLineSerializer(serializers.ModelSerializer):
    product = serializers.CharField(source="variant.name")

    class Meta:
        model = SubscriptionLine
        fields = ["product", "quantity", "unit_price", "amount_untaxed", "amount_tax", "amount_total"]


class SubscriptionSerializer(serializers.ModelSerializer):
    customer = serializers.CharField(source="customer.name")
    plan = serializers.CharField(source="plan.name")
    billing_period = serializers.CharField(source="plan.billing_period")
    lines = SubscriptionLineSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id", "number", "customer", "plan", "billing_period", "status", "start_date", "expiry_date",
            "next_invoice_date", "payment_term_days", "amount_untaxed", "amount_tax", "amount_total", "mrr", "lines",
        ]


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = ["description", "quantity", "unit_price", "discount_amount", "tax_rate", "amount_untaxed", "amount_tax", "amount_total"]


class InvoiceSerializer(serializers.ModelSerializer):
    subscription = serializers.CharField(source="subscription.number", default=None)
    payment_state = serializers.CharField(read_only=True)
    amount_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "customer_name", "subscription", "status", "payment_state", "invoice_date", "due_date",
            "period_start", "period_end", "amount_untaxed", "amount_discount", "amount_tax", "amount_total",
            "amount_paid", "amount_due", "lines",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    invoice = serializers.CharField(source="invoice.number")
    customer = serializers.CharField(source="customer.name")

    class Meta:
        model = Payment
        fields = ["id", "number", "invoice", "customer", "method", "amount", "payment_date", "reference", "note"]
