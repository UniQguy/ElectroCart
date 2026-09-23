from django.contrib import admin
from .models import (
    UserProfile,
    Product,
    ProductImage,
    ProductSpecification,
    ProductVariant,
    Cart,
    CartItem,
    Order,
    OrderItem
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductSpecificationInline(admin.TabularInline):
    model = ProductSpecification
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_code', 'category', 'brand', 'price', 'mrp', 'stock', 'is_featured')
    list_filter = ('category', 'brand', 'is_featured')
    search_fields = ('name', 'product_code', 'api_sku', 'brand')
    inlines = [ProductImageInline, ProductSpecificationInline, ProductVariantInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session_key', 'total_items', 'total_price', 'created_at')
    search_fields = ('session_key', 'user__username')
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'price', 'quantity', 'line_total')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'user__username', 'phone')
    inlines = [OrderItemInline]


admin.site.register(UserProfile)