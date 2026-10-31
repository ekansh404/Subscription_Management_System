from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("revenue/", views.RevenueReportView.as_view(), name="revenue"),
    path("revenue.csv", views.RevenueCsvView.as_view(), name="revenue_csv"),
]
