from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("", views.SubscriptionListView.as_view(), name="subscription_list"),
    path("new/", views.SubscriptionEditView.as_view(), name="subscription_create"),
    path("from-template/", views.SubscriptionFromTemplateView.as_view(), name="subscription_from_template"),
    path("<int:pk>/", views.SubscriptionDetailView.as_view(), name="subscription_detail"),
    path("<int:pk>/edit/", views.SubscriptionEditView.as_view(), name="subscription_update"),
    path("<int:pk>/<slug:action>/", views.SubscriptionActionView.as_view(), name="subscription_action"),
    path("templates/", views.TemplateListView.as_view(), name="template_list"),
    path("templates/new/", views.TemplateEditView.as_view(), name="template_create"),
    path("templates/<int:pk>/edit/", views.TemplateEditView.as_view(), name="template_update"),
]
