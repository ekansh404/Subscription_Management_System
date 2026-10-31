from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="payment_list"),
    path("<int:pk>/receipt/", views.PaymentReceiptView.as_view(), name="payment_receipt"),
    path("invoices/<int:invoice_pk>/pay/", views.RecordPaymentView.as_view(), name="payment_create"),
    path("invoices/<int:invoice_pk>/remind/", views.SendReminderView.as_view(), name="payment_remind"),
    path("receivables/", views.ReceivablesView.as_view(), name="receivables"),
]
