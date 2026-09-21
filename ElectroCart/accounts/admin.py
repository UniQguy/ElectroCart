from django.contrib import admin
from django import forms
from django.core.files.base import ContentFile

from urllib.request import Request, urlopen
from urllib.parse import urlparse
import os


from .models import (
    UserProfile,
    Product,
    ProductSpecification,
    ProductImage,
    Cart,
    CartItem,
    Wishlist,
    WishlistItem,
    ProductVariant,
    Order,
    OrderItem,
)


# ============================================================
# PRODUCT ADMIN FORM
# ============================================================

class ProductAdminForm(forms.ModelForm):

    image_url = forms.URLField(
        required=False,
        label="Image URL",
        widget=forms.URLInput(
            attrs={
                "placeholder": "https://example.com/product.jpg",
                "style": "width: 500px;"
            }
        )
    )

    class Meta:
        model = Product
        fields = "__all__"

    def save(self, commit=True):

        instance = super().save(commit=False)

        image_url = (self.cleaned_data.get("image_url") or "").strip()

        if image_url and not instance.image:

            try:

                request = Request(
                    image_url,
                    headers={
                        "User-Agent": "Mozilla/5.0"
                    }
                )

                with urlopen(request, timeout=15) as response:
                    image_data = response.read()

                # VERIFY ACTUAL IMAGE
                from PIL import Image
                from io import BytesIO

                try:
                    image = Image.open(BytesIO(image_data))
                    image.verify()

                except Exception:
                    raise ValueError(
                        "URL returned an invalid or blocked image."
                    )

                # Get proper extension
                extension = image.format.lower()

                extension_map = {
                    "JPEG": ".jpg",
                    "PNG": ".png",
                    "WEBP": ".webp",
                    "GIF": ".gif",
                    "AVIF": ".avif",
                }

                file_extension = extension_map.get(
                    image.format.upper(),
                    ".jpg"
                )

                filename = os.path.basename(
                    urlparse(image_url).path
                )

                filename = os.path.splitext(filename)[0]

                if not filename:
                    filename = "product_image"

                filename += file_extension

                instance.image.save(
                    filename,
                    ContentFile(image_data),
                    save=False
                )

            except Exception as error:

                raise forms.ValidationError(
                    f"Could not download image: {error}"
                )

        if commit:
            instance.save()

        return instance


# ============================================================
# ADMIN
# ============================================================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "phone",
        "city",
        "created_at"
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    form = ProductAdminForm

    list_display = (
        "name",
        "category",
        "price",
        "mrp",
        "quantity",
        "is_active"
    )

    list_filter = (
        "category",
        "is_active"
    )

    search_fields = (
        "name",
        "description",
        "category"
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "created_at",
        "updated_at"
    )


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):

    list_display = (
        "cart",
        "product",
        "quantity"
    )


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "created_at"
    )


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):

    list_display = (
        "wishlist",
        "product",
        "added_at"
    )


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "image"
    )

    list_filter = (
        "product",
    )


@admin.register(ProductSpecification)
class ProductSpecificationAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "name",
        "value"
    )

    list_filter = (
        "name",
    )

    search_fields = (
        "product__name",
        "name",
        "value"
    )


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):

    list_display = (
        "product",
        "name",
        "sku",
        "price",
        "quantity",
        "is_active",
    )

    list_filter = (
        "is_active",
        "product",
    )

    search_fields = (
        "product__name",
        "name",
        "sku",
    )

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        "order_number",
        "customer_name",
        "email",
        "phone",
        "total",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "created_at",
    )

    search_fields = (
        "order_number",
        "customer_name",
        "email",
        "phone",
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "product_name",
        "variant_name",
        "sku",
        "quantity",
        "unit_price",
        "total_price",
    )

    search_fields = (
        "order__order_number",
        "product_name",
        "sku",
    )   

