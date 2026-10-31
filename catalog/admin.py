from django.contrib import admin

from .models import AttributeValue, Plan, Product, ProductAttribute, ProductVariant, Tax


class AttributeValueInline(admin.TabularInline):
    model = AttributeValue
    extra = 1


@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    inlines = [AttributeValueInline]


class VariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("name", "price_extra", "is_active")
    readonly_fields = ("name", "price_extra")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_type", "sales_price", "cost_price", "is_active")
    list_filter = ("product_type", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("taxes", "attribute_values")
    inlines = [VariantInline]


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "billing_period", "min_quantity", "start_date", "end_date", "is_active")
    list_filter = ("billing_period", "is_active")


admin.site.register(Tax)
