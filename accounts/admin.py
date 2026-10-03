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
    OrderItem,
    Wishlist,
    WishlistItem,
    CompetitorPrice,
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


class CompetitorPriceInline(admin.TabularInline):
    model = CompetitorPrice
    extra = 0
    readonly_fields = ('extracted_at',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_code', 'category', 'brand', 'price', 'mrp', 'stock', 'rating', 'is_featured', 'created_at')
    list_filter = ('category', 'brand', 'is_featured', 'created_at')
    search_fields = ('name', 'product_code', 'api_sku', 'brand', 'description')
    list_editable = ('price', 'stock', 'is_featured')
    inlines = [ProductImageInline, ProductSpecificationInline, ProductVariantInline, CompetitorPriceInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('line_total', 'added_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'session_key', 'total_items', 'total_price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('session_key', 'user__username', 'user__email')
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'product_name', 'price', 'quantity', 'line_total')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'display_name', 'customer_email', 'total_amount', 'status', 'city', 'created_at')
    list_filter = ('status', 'created_at', 'state')
    search_fields = ('order_number', 'customer_name', 'customer_email', 'user__username', 'phone', 'city', 'pincode')
    readonly_fields = ('order_number', 'total_amount', 'discount', 'created_at', 'updated_at')
    inlines = [OrderItemInline]

    @admin.display(description='Customer')
    def display_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return getattr(obj, 'customer_name', '') or "Guest"


class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0
    readonly_fields = ('product', 'added_at')


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__username', 'user__email')
    inlines = [WishlistItemInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'city', 'state', 'pincode', 'created_at')
    search_fields = ('user__username', 'user__email', 'phone', 'city', 'pincode')
    list_filter = ('state', 'created_at')


@admin.register(CompetitorPrice)
class CompetitorPriceAdmin(admin.ModelAdmin):
    list_display = ('product', 'merchant_name', 'price', 'extracted_at')
    list_filter = ('merchant_name', 'extracted_at')
    search_fields = ('product__name', 'merchant_name')