from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "api"

router = DefaultRouter()
router.register("customers", views.CustomerViewSet, basename="customer")
router.register("products", views.ProductViewSet, basename="product")
router.register("plans", views.PlanViewSet, basename="plan")
router.register("subscriptions", views.SubscriptionViewSet, basename="subscription")
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("payments", views.PaymentViewSet, basename="payment")

urlpatterns = [
    path("kpis/", views.KpiView.as_view(), name="kpis"),
    path("", include(router.urls)),
]
