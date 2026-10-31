from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("healthz/", views.healthcheck, name="healthcheck"),
    path("outbox/", views.OutboxListView.as_view(), name="outbox"),
    path("outbox/<int:pk>/", views.OutboxDetailView.as_view(), name="outbox_detail"),
]
