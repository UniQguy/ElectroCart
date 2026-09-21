from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_POST

import json
from decimal import Decimal
from django.db import transaction

from .models import (
    UserProfile,
    Product,
    ProductVariant,
    Cart,
    CartItem,
    Wishlist,
    WishlistItem,
    Order,
    OrderItem,
)


# ============================================================
# SPLASH
# ============================================================

def splash(request):

    # If already logged in, go directly to home
    if request.user.is_authenticated:
        return redirect("home")

    return render(
        request,
        "accounts/splash.html"
    )


# ============================================================
# LOGIN
# ============================================================

# ============================================================
# LOGIN
# ============================================================

def login_user(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not email or not password:
            messages.error(request, "Please enter your email and password.")
        else:
            user = authenticate(
                request,
                username=email,
                password=password
            )

            if user is not None:
                login(request, user, backend="accounts.backends.EmailOrPhoneBackend")
                return redirect("home")

            messages.error(request, "Invalid email or password.")

    return render(request, "accounts/login.html")




# ============================================================
# SIGN UP
# ============================================================

def signup_user(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not all([name, email, phone, password, confirm_password]):
            messages.error(request, "Please fill in all fields.")

        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")

        elif User.objects.filter(email__iexact=email).exists():
            messages.error(
                request,
                "An account with this email already exists."
            )

        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name
            )

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save()

            login(request, user, backend="accounts.backends.EmailOrPhoneBackend")

            return redirect("home")

    return render(request, "accounts/signup.html")

# ============================================================
# CHECKOUT
# ============================================================

@login_required
def checkout(request):

    if request.method == "POST":

        try:
            cart = json.loads(request.body)

            if not cart:
                return JsonResponse({
                    "success": False,
                    "message": "Your bag is empty."
                }, status=400)

            # CUSTOMER DETAILS
            data = json.loads(request.body)

            cart = data.get("cart", [])

            customer_name = data.get("customer_name", "").strip()
            email = data.get("email", "").strip()
            phone = data.get("phone", "").strip()

            address = data.get("address", "").strip()
            city = data.get("city", "").strip()
            state = data.get("state", "").strip()
            pincode = data.get("pincode", "").strip()

            # Basic validation
            if not all([
                customer_name,
                email,
                phone,
                address,
                city,
                state,
                pincode
            ]):
                return JsonResponse({
                    "success": False,
                    "message": "Please complete all customer and delivery details."
                }, status=400)

            if not pincode.isdigit() or len(pincode) != 6:
                return JsonResponse({
                    "success": False,
                    "message": "Pincode must contain exactly 6 digits."
                }, status=400)

            subtotal = Decimal("0.00")

            with transaction.atomic():

                order = Order.objects.create(
                    order_number=f"EC-{request.user.id}-{Order.objects.count() + 1:05d}",
                    user=request.user,
                    customer_name=customer_name,
                    email=email,
                    phone=phone,
                    address=address,
                    city=city,
                    state=state,
                    pincode=pincode,
                    subtotal=Decimal("0.00"),
                    discount=Decimal("0.00"),
                    total=Decimal("0.00"),
                    status="Pending",
                )

                for item in cart:

                    product_id = item.get("id")
                    quantity = int(item.get("qty", 0))
                    variant_id = item.get("variantId")

                    if quantity < 1:
                        raise ValueError("Invalid product quantity.")

                    product = Product.objects.select_for_update().filter(
                        id=product_id,
                        is_active=True
                    ).first()

                    if not product:
                        raise ValueError(
                            "A product in your bag is no longer available."
                        )

                    variant = None

                    if variant_id:
                        variant = ProductVariant.objects.select_for_update().filter(
                            id=variant_id,
                            product=product,
                            is_active=True
                        ).first()

                        if not variant:
                            raise ValueError(
                                f"Variant for {product.name} is no longer available."
                            )

                        if quantity > variant.quantity:
                            raise ValueError(
                                f"{variant.name}: only {variant.quantity} unit(s) available."
                            )

                        unit_price = variant.price
                        sku = variant.sku
                        variant_name = variant.name

                    else:

                        if quantity > product.quantity:
                            raise ValueError(
                                f"{product.name}: only {product.quantity} unit(s) available."
                            )

                        unit_price = product.price
                        sku = product.product_code or f"EC-{product.id}"
                        variant_name = ""

                    item_total = unit_price * quantity
                    subtotal += item_total

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        variant=variant,
                        product_name=product.name,
                        variant_name=variant_name,
                        sku=sku,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=item_total,
                    )

                    if variant:
                        variant.quantity -= quantity
                        variant.save(update_fields=["quantity"])
                    else:
                        product.quantity -= quantity
                        product.save(update_fields=["quantity"])

                order.subtotal = subtotal
                order.total = subtotal
                order.save(
                    update_fields=[
                        "subtotal",
                        "total"
                    ]
                )

            return JsonResponse({
                "success": True,
                "order_number": order.order_number
            })

        except Exception as error:

            return JsonResponse({
                "success": False,
                "message": str(error)
            }, status=400)

    return render(
        request,
        "accounts/checkout.html"
    )   


# ============================================================
# HOME
# ============================================================

def home(request):

    products = Product.objects.filter(
        is_active=True
    )

    wishlist_ids = set()

    cart_items = {}

    if request.user.is_authenticated:

        wishlist, _ = Wishlist.objects.get_or_create(
            user=request.user
        )

        wishlist_ids = set(
            wishlist.items.values_list(
                "product_id",
                flat=True
            )
        )

        cart, _ = Cart.objects.get_or_create(
            user=request.user
        )

        cart_items = {
            item.product_id: item.quantity
            for item in cart.items.all()
        }

        product_ids = {
            p.name: p.id
            for p in Product.objects.filter(is_active=True)
        }

    context = {
        "products": products,
        "wishlist_ids": wishlist_ids,
        "cart_items": cart_items,
        "product_ids": product_ids,
    }

    return render(
        request,
        "accounts/home.html",
        context
    )


# ============================================================
# CART
# ============================================================

@login_required
@require_POST
def add_to_cart(request):

    product_id = request.POST.get(
        "product_id"
    )

    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    variants = product.variants.filter(
        is_active=True
    ).order_by("price")

    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product
    )

    if not created:

        if item.quantity < product.quantity:

            item.quantity += 1
            item.save()

    else:

        item.quantity = 1
        item.save()

    return cart_response(request)


# ============================================================
# UPDATE CART
# ============================================================

@login_required
@require_POST
def update_cart(request):

    product_id = request.POST.get(
        "product_id"
    )

    action = request.POST.get(
        "action"
    )

    cart = get_object_or_404(
        Cart,
        user=request.user
    )

    item = get_object_or_404(
        CartItem,
        cart=cart,
        product_id=product_id
    )

    if action == "increase":

        if item.quantity < item.product.quantity:

            item.quantity += 1
            item.save()

    elif action == "decrease":

        if item.quantity > 1:

            item.quantity -= 1
            item.save()

        else:

            item.delete()

    elif action == "remove":

        item.delete()

    return cart_response(request)


# ============================================================
# CART DATA
# ============================================================

@login_required
def cart_data(request):

    return cart_response(request)


# ============================================================
# CHECKOUT STOCK VALIDATION
# ============================================================

@login_required
@require_POST
def validate_checkout_stock(request):

    import json

    try:
        cart = json.loads(request.body)
    except:
        return JsonResponse({
            "success": False,
            "message": "Invalid cart data."
        }, status=400)

    for item in cart:

        product_id = item.get("id")
        quantity = int(item.get("qty", 0))

        product = Product.objects.filter(
            id=product_id,
            is_active=True
        ).first()

        if not product:
            return JsonResponse({
                "success": False,
                "message": "A product in your bag is no longer available."
            })

        if quantity > product.quantity:
            return JsonResponse({
                "success": False,
                "message": f"{product.name}: only {product.quantity} unit(s) available."
            })

    return JsonResponse({
        "success": True
    })



# @login_required
def cart_response(request):

    cart, _ = Cart.objects.get_or_create(
        user=request.user
    )

    items = []

    for item in cart.items.select_related("product"):

        items.append({

            "id": item.product.id,

            "name": item.product.name,

            "description": item.product.description,

            "price": float(
                item.product.price
            ),

            "mrp": float(
                item.product.mrp
            ),

            "quantity": item.quantity,

            "total": float(
                item.total_price
            ),

            "image": (
                item.product.image.url
                if item.product.image
                else ""
            )

        })

    return JsonResponse({

        "success": True,

        "items": items,

        "total_items": cart.total_items,

        "subtotal": float(
            cart.subtotal
        )

    })


# ============================================================
# WISHLIST
# ============================================================

@login_required
@require_POST
def toggle_wishlist(request):

    product_id = request.POST.get(
        "product_id"
    )

    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    wishlist, _ = Wishlist.objects.get_or_create(
        user=request.user
    )

    item = WishlistItem.objects.filter(
        wishlist=wishlist,
        product=product
    ).first()

    if item:

        item.delete()
        added = False

    else:

        WishlistItem.objects.create(
            wishlist=wishlist,
            product=product
        )

        added = True

    count = wishlist.items.count()

    return JsonResponse({

        "success": True,

        "added": added,

        "count": count

    })


@login_required
def wishlist_data(request):

    wishlist, _ = Wishlist.objects.get_or_create(
        user=request.user
    )

    items = []

    for item in wishlist.items.select_related("product"):

        product = item.product

        items.append({
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": float(product.price),
        "mrp": float(product.mrp),
        "stock": product.quantity,
        "sku": product.product_code or f"EC-{product.id}",
        "has_variants": product.variants.exists(),
        "image": (
            product.image.url
            if product.image
            else ""
        )
    })

    return JsonResponse({

        "success": True,

        "items": items,

        "count": len(items)

    })


# ============================================================
# LOGOUT
# ============================================================

@login_required
def logout_user(request):

    logout(request)

    return redirect("splash")

@login_required
def account_hub(request):
    return render(
        request,
        "accounts/account_hub.html"
    )


def product_details(request):
    product_id = request.GET.get("id")

    product = get_object_or_404(
        Product,
        id=product_id,
        is_active=True
    )

    variants = product.variants.filter(
        is_active=True
    ).order_by("price")

    # =========================================================
    # RECENTLY VIEWED PRODUCTS
    # =========================================================

    recently_viewed = request.session.get("recently_viewed", [])

    recently_viewed = [
        product_id
        for product_id in recently_viewed
        if str(product_id) != str(product.id)
    ]

    recently_viewed.insert(0, product.id)

    # Keep latest 8
    recently_viewed = recently_viewed[:8]

    request.session["recently_viewed"] = recently_viewed
    request.session.modified = True

    # Previous products only
    previously_viewed = [
        product_id
        for product_id in recently_viewed
        if str(product_id) != str(product.id)
    ]

    recently_viewed_products = list(
        Product.objects.filter(
            id__in=previously_viewed,
            is_active=True
        )
    )

    recently_viewed_products.sort(
        key=lambda item: previously_viewed.index(item.id)
    )

    # =========================================================
    # RELATED PRODUCTS
    # =========================================================

    related_products = (
        Product.objects
        .filter(
            category=product.category,
            is_active=True
        )
        .exclude(id=product.id)
        .order_by("-created_at")[:4]
    )

    return render(
        request,
        "accounts/product_details.html",
        {
            "product": product,
            "variants": variants,
            "related_products": related_products,
            "recently_viewed_products": recently_viewed_products,
        }
    )


@login_required
def orders(request):
    return render(request, "accounts/orders.html")


@login_required
def wishlist_page(request):
    return render(request, "accounts/wishlist.html")


@login_required
def addresses(request):
    return render(request, "accounts/addresses.html")


@login_required
def cart_page(request):
    return render(request, "accounts/cart.html")


@login_required
def order_confirmation(request):
    return render(
        request,
        "accounts/order_confirmation.html"
    )