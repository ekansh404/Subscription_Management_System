"""
Read-only REST API (Django REST Framework, session authentication).

Staff and admins read everything. Customers can read their own
subscriptions, invoices and payments, the same data the portal shows.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Invoice, InvoiceStatus
from catalog.models import Plan, Product
from customers.models import Customer
from customers.services import customer_for_user
from payments.models import Payment
from reports import services as reports
from subscriptions.models import Status, Subscription

from . import serializers
from .permissions import IsStaffMember


class StaffReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsStaffMember]


class CustomerScopedViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff see all rows; a customer sees only rows belonging to them."""

    permission_classes = [IsAuthenticated]
    customer_field = "customer"
    hidden_for_customers = {}

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_staff_member:
            return queryset
        customer = customer_for_user(user)
        if customer is None:
            return queryset.none()
        return queryset.filter(**{self.customer_field: customer}).exclude(**self.hidden_for_customers)


class CustomerViewSet(StaffReadOnlyViewSet):
    queryset = Customer.objects.all()
    serializer_class = serializers.CustomerSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get("search")
        return queryset.filter(name__icontains=search) if search else queryset


class ProductViewSet(StaffReadOnlyViewSet):
    queryset = Product.objects.prefetch_related("variants", "taxes")
    serializer_class = serializers.ProductSerializer


class PlanViewSet(StaffReadOnlyViewSet):
    queryset = Plan.objects.all()
    serializer_class = serializers.PlanSerializer


class SubscriptionViewSet(CustomerScopedViewSet):
    queryset = Subscription.objects.select_related("customer", "plan").prefetch_related("lines__variant")
    serializer_class = serializers.SubscriptionSerializer
    hidden_for_customers = {"status": Status.DRAFT}

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset


class InvoiceViewSet(CustomerScopedViewSet):
    queryset = Invoice.objects.select_related("subscription").prefetch_related("lines")
    serializer_class = serializers.InvoiceSerializer
    hidden_for_customers = {"status": InvoiceStatus.DRAFT}

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset


class PaymentViewSet(CustomerScopedViewSet):
    queryset = Payment.objects.select_related("invoice", "customer")
    serializer_class = serializers.PaymentSerializer


class KpiView(APIView):
    """Dashboard numbers for the default period (last six months)."""

    permission_classes = [IsStaffMember]

    def get(self, request):
        filters = reports.ReportFilters.default()
        kpi = reports.kpis(filters)
        return Response(
            {
                "period": {"from": filters.date_from, "to": filters.date_to},
                "active_subscriptions": kpi["subscriptions"]["active"],
                "mrr": kpi["subscriptions"]["mrr"],
                "arr": kpi["arr"],
                "invoiced": kpi["billed"]["invoiced"],
                "collected": kpi["collected"]["amount"],
                "outstanding": kpi["outstanding"]["amount"],
                "overdue": kpi["overdue"]["amount"],
                "overdue_invoices": kpi["overdue"]["count"],
            }
        )
