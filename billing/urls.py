from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/confirm-drafts/", views.ConfirmDraftsView.as_view(), name="invoice_confirm_drafts"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/print/", views.InvoicePrintView.as_view(), name="invoice_print"),
    path("invoices/<int:pk>/<slug:action>/", views.InvoiceActionView.as_view(), name="invoice_action"),
    path("run/", views.BillingRunView.as_view(), name="run"),
    path("subscriptions/<int:pk>/invoice/", views.SubscriptionInvoiceNowView.as_view(), name="subscription_invoice"),
    path("subscriptions/<int:pk>/discount/", views.SubscriptionDiscountView.as_view(), name="subscription_discount"),
    path("discounts/", views.DiscountListView.as_view(), name="discount_list"),
    path("discounts/new/", views.DiscountCreateView.as_view(), name="discount_create"),
    path("discounts/<int:pk>/edit/", views.DiscountUpdateView.as_view(), name="discount_update"),
]
