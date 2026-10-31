from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.PortalHomeView.as_view(), name="home"),
    path("subscriptions/", views.PortalSubscriptionListView.as_view(), name="subscription_list"),
    path("subscriptions/<int:pk>/", views.PortalSubscriptionDetailView.as_view(), name="subscription_detail"),
    path("subscriptions/<int:pk>/<slug:action>/", views.PortalSubscriptionActionView.as_view(), name="subscription_action"),
    path("invoices/", views.PortalInvoiceListView.as_view(), name="invoice_list"),
    path("invoices/<int:pk>/", views.PortalInvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/print/", views.PortalInvoicePrintView.as_view(), name="invoice_print"),
    path("payments/", views.PortalPaymentListView.as_view(), name="payment_list"),
]
