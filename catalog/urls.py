from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("plans/", views.PlanListView.as_view(), name="plan_list"),
    path("plans/new/", views.PlanCreateView.as_view(), name="plan_create"),
    path("plans/<int:pk>/", views.PlanDetailView.as_view(), name="plan_detail"),
    path("plans/<int:pk>/edit/", views.PlanUpdateView.as_view(), name="plan_update"),
    path("taxes/", views.TaxListView.as_view(), name="tax_list"),
    path("taxes/new/", views.TaxCreateView.as_view(), name="tax_create"),
    path("taxes/<int:pk>/edit/", views.TaxUpdateView.as_view(), name="tax_update"),
    path("attributes/", views.AttributeListView.as_view(), name="attribute_list"),
    path("attributes/new/", views.AttributeFormView.as_view(), name="attribute_create"),
    path("attributes/<int:pk>/edit/", views.AttributeFormView.as_view(), name="attribute_update"),
]
