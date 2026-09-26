import uuid
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from .models import (
    Product,
    ProductImage,
    Cart,
    CartItem,
    Order,
    OrderItem,
    UserProfile,
    Wishlist,
    WishlistItem,
    CompetitorPrice,
)
from .services import fetch_live_market_radar


def splash(request):
    """Fallback redirect to storefront catalog."""
    return redirect('home')


def get_or_create_cart(request):
    """Retrieves or creates a cart bound to either the authenticated User or Session key."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    if not request.session.session_key:
        request.session.create()

    cart_id = request.session.get('cart_id')
    if cart_id:
        cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
        if cart:
            if cart.session_key != request.session.session_key:
                cart.session_key = request.session.session_key
                cart.save(update_fields=['session_key'])
            return cart

    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user__isnull=True)
    request.session['cart_id'] = cart.id
    request.session.modified = True
    return cart


def home(request):
    """Master Catalog view rendering all 62 products without mandatory login."""
    featured_products = Product.objects.filter(is_featured=True)[:6]
    all_products = Product.objects.all().order_by('-created_at')
    categories = Product.objects.values_list('category', flat=True).distinct()
    cart = get_or_create_cart(request)

    context = {
        'featured_products': featured_products,
        'products': all_products,
        'categories': categories,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/home.html', context)


def category_view(request, category_name):
    """Filters products by category with public access."""
    products = Product.objects.filter(category__iexact=category_name)
    categories = Product.objects.values_list('category', flat=True).distinct()
    cart = get_or_create_cart(request)

    context = {
        'category_name': category_name,
        'products': products,
        'categories': categories,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/home.html', context)


def product_details(request, pk=None):
    """
    Renders product detail page.
    Supports pk from URL route OR ?id=... query parameter from home.html.
    """
    product_id = pk or request.GET.get('id') or request.GET.get('product_id')
    if not product_id:
        product = Product.objects.first()
        if not product:
            return redirect('home')
    else:
        product = get_object_or_404(Product, pk=product_id)

    gallery = product.gallery_images.all()
    specs = product.specifications.all()
    cart = get_or_create_cart(request)

    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = WishlistItem.objects.filter(wishlist__user=request.user, product=product).exists()

    market_benchmark = fetch_live_market_radar(product)
    lowest_competitor = market_benchmark.first() if market_benchmark.exists() else None
    savings_vs_market = None
    if lowest_competitor and lowest_competitor.price > product.price:
        savings_vs_market = lowest_competitor.price - product.price

    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]

    context = {
        'product': product,
        'gallery': gallery,
        'specs': specs,
        'cart_count': cart.total_items,
        'in_wishlist': in_wishlist,
        'market_benchmark': market_benchmark,
        'lowest_competitor': lowest_competitor,
        'savings_vs_market': savings_vs_market,
        'related_products': related_products,
    }
    return render(request, 'accounts/product_details.html', context)


def cart_view(request):
    """Public Cart View with session-backed item persistence."""
    cart = get_or_create_cart(request)
    items = cart.items.select_related('product').all()

    context = {
        'cart': cart,
        'items': items,
        'total_price': cart.total_price,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/cart.html', context)


def add_to_cart(request, product_id=None):
    """Adds product to cart via URL parameter, POST body, or JSON payload."""
    if not product_id:
        product_id = request.POST.get('product_id') or request.GET.get('product_id') or request.GET.get('id')
        if not product_id and request.body:
            try:
                data = json.loads(request.body)
                product_id = data.get('product_id') or data.get('id')
            except Exception:
                pass

    product = get_object_or_404(Product, id=product_id)
    cart = get_or_create_cart(request)

    if product.stock <= 0:
        messages.error(request, f"{product.name} is out of stock.")
        return redirect(request.META.get('HTTP_REFERER', 'home'))

    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        if cart_item.quantity < product.stock:
            cart_item.quantity += 1
            cart_item.save(update_fields=['quantity'])
            messages.success(request, f"Updated quantity for {product.name}.")
        else:
            messages.warning(request, f"Cannot exceed available stock of {product.stock}.")
    else:
        messages.success(request, f"Added {product.name} to bag.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'cart_count': cart.total_items,
            'cart_total': str(cart.total_price)
        })

    return redirect(request.META.get('HTTP_REFERER', 'cart_view'))


def update_cart_quantity(request, item_id=None):
    if not item_id:
        item_id = request.POST.get('item_id') or request.GET.get('item_id')
    cart = get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    action = request.POST.get('action') or request.GET.get('action')

    if action == 'increase':
        if cart_item.quantity < cart_item.product.stock:
            cart_item.quantity += 1
            cart_item.save(update_fields=['quantity'])
        else:
            messages.warning(request, f"Stock limit reached for {cart_item.product.name}.")
    elif action == 'decrease':
        cart_item.quantity -= 1
        if cart_item.quantity <= 0:
            cart_item.delete()
        else:
            cart_item.save(update_fields=['quantity'])

    return redirect('cart_view')


def remove_from_cart(request, item_id=None):
    if not item_id:
        item_id = request.POST.get('item_id') or request.GET.get('item_id')
    cart = get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    cart_item.delete()
    messages.info(request, "Item removed from bag.")
    return redirect('cart_view')


def wishlist_view(request):
    cart = get_or_create_cart(request)
    if request.user.is_authenticated:
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        wishlist_items = wishlist.items.select_related('product').all()
    else:
        wishlist_items = []

    context = {
        'items': wishlist_items,
        'wishlist_items': wishlist_items,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/wishlist.html', context)


def wishlist_data(request):
    if request.user.is_authenticated:
        try:
            wishlist = Wishlist.objects.get(user=request.user)
            ids = list(wishlist.items.values_list('product_id', flat=True))
        except Wishlist.DoesNotExist:
            ids = []
    else:
        ids = []
    return JsonResponse({'wishlist_ids': ids})


def toggle_wishlist(request, product_id=None):
    if not request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'auth_required', 'redirect_url': '/login/'}, status=401)
        messages.info(request, "Please sign in to manage your saved collection.")
        return redirect('login')

    if not product_id:
        product_id = request.POST.get('product_id') or request.GET.get('product_id')
        if not product_id and request.body:
            try:
                data = json.loads(request.body)
                product_id = data.get('product_id')
            except Exception:
                pass

    product = get_object_or_404(Product, id=product_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    existing_item = wishlist.items.filter(product=product).first()

    if existing_item:
        existing_item.delete()
        is_saved = False
        messages.info(request, f"Removed {product.name} from your collection.")
    else:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        is_saved = True
        messages.success(request, f"Saved {product.name} to your collection.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.method == 'POST':
        return JsonResponse({
            'status': 'success',
            'is_saved': is_saved,
            'wishlist_count': wishlist.items.count()
        })

    return redirect(request.META.get('HTTP_REFERER', 'wishlist_page'))


@login_required
def addresses_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    cart = get_or_create_cart(request)

    if request.method == 'POST':
        profile.address = request.POST.get('address', profile.address).strip()
        profile.city = request.POST.get('city', profile.city).strip()
        profile.state = request.POST.get('state', profile.state).strip()
        profile.pincode = request.POST.get('pincode', profile.pincode).strip()
        profile.phone = request.POST.get('phone', profile.phone).strip()
        profile.save()
        messages.success(request, "Delivery parameters updated.")
        return redirect('addresses')

    context = {
        'profile': profile,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/addresses.html', context)


@transaction.atomic
def checkout_view(request):
    """
    Frictionless Checkout: Allows both authenticated users AND guest visitors to checkout.
    Zero forced redirects to /login/.
    """
    cart = get_or_create_cart(request)
    items = cart.items.select_related('product').all()

    if not items.exists():
        messages.warning(request, "Your bag is empty.")
        return redirect('home')

    profile = None
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        name = (request.POST.get('name') or request.POST.get('customer_name') or '').strip()
        email = (request.POST.get('email') or '').strip()
        address = (request.POST.get('address') or request.POST.get('shipping_address') or (profile.address if profile else '') or 'Standard Delivery Address').strip()
        city = (request.POST.get('city') or (profile.city if profile else '') or 'Ahmedabad').strip()
        state = (request.POST.get('state') or (profile.state if profile else '') or 'Gujarat').strip()
        pincode = (request.POST.get('pincode') or request.POST.get('zip_code') or (profile.pincode if profile else '') or '380009').strip()
        phone = (request.POST.get('phone') or request.POST.get('contact_number') or (profile.phone if profile else '') or '9999999999').strip()

        if profile:
            profile.address = address
            profile.city = city
            profile.state = state
            profile.pincode = pincode
            profile.phone = phone
            profile.save()

        # Database row-level locking concurrency guard
        for item in items:
            locked_product = Product.objects.select_for_update().get(id=item.product.id)
            if locked_product.stock < item.quantity:
                messages.error(request, f"Insufficient stock for {locked_product.name}. Remaining: {locked_product.stock}.")
                return render(request, 'accounts/checkout.html', {
                    'cart': cart,
                    'items': items,
                    'profile': profile,
                    'total_price': cart.total_price
                })

            locked_product.stock -= item.quantity
            locked_product.save(update_fields=['stock'])

        order_num = f"EC-{uuid.uuid4().hex[:8].upper()}"
        order = Order.objects.create(
            user=request.user if request.user.is_authenticated else None,
            order_number=order_num,
            total_amount=cart.total_price,
            shipping_address=address,
            city=city,
            state=state,
            pincode=pincode,
            phone=phone,
            status='CONFIRMED'
        )

        for item in items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                price=item.product.price,
                quantity=item.quantity
            )

        if not request.user.is_authenticated:
            request.session['guest_customer_name'] = name or 'Guest Patron'
            request.session['guest_customer_email'] = email

        items.delete()
        request.session['last_order_number'] = order.order_number
        return redirect('order_confirmation', order_number=order.order_number)

    return render(request, 'accounts/checkout.html', {
        'cart': cart,
        'items': items,
        'profile': profile,
        'total_price': cart.total_price
    })


def order_confirmation_view(request, order_number=None):
    """Renders dynamic Order and OrderItem invoices with verified ownership checks."""
    if not order_number:
        order_number = request.session.get('last_order_number')

    if not order_number and request.user.is_authenticated:
        latest = Order.objects.filter(user=request.user).first()
        if latest:
            order_number = latest.order_number

    if not order_number:
        return redirect('home')

    order = get_object_or_404(
        Order.objects.prefetch_related('items__product'),
        order_number=order_number
    )

    is_owner = (request.user.is_authenticated and order.user == request.user)
    is_session_order = (request.session.get('last_order_number') == order.order_number)

    if not (is_owner or is_session_order or (request.user.is_authenticated and request.user.is_staff)):
        messages.error(request, "Access unauthorized for this order invoice.")
        return redirect('home')

    guest_name = request.session.get('guest_customer_name', 'Guest Patron')

    context = {
        'order': order,
        'order_items': order.items.all(),
        'subtotal': order.total_amount,
        'guest_name': guest_name,
    }
    return render(request, 'accounts/order_confirmation.html', context)


@login_required
def orders_history_view(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product')
    return render(request, 'accounts/orders.html', {'orders': orders})


@login_required
def account_hub(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    recent_orders = Order.objects.filter(user=request.user)[:3]
    return render(request, 'accounts/account_hub.html', {'profile': profile, 'recent_orders': recent_orders})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next') or request.POST.get('next') or 'home'

    if request.method == 'POST':
        # Accept username, identifier, email, or phone from the form
        u = (request.POST.get('username') or request.POST.get('identifier') or request.POST.get('email') or '').strip()
        p = (request.POST.get('password') or request.POST.get('access_key') or '').strip()
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            messages.success(request, f"Authenticated as {user.username}.")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid credentials or access key.")

    return render(request, 'accounts/login.html', {'next': next_url})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next') or request.POST.get('next') or 'home'

    if request.method == 'POST':
        u = request.POST.get('username', '').strip()
        e = request.POST.get('email', '').strip()
        p1 = request.POST.get('password', '').strip()
        p2 = request.POST.get('confirm_password', '').strip()

        if p1 != p2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        if User.objects.filter(username=u).exists():
            messages.error(request, "Username already taken.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        user = User.objects.create_user(username=u, email=e, password=p1)
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect(next_url)

    return render(request, 'accounts/signup.html', {'next': next_url})


def logout_view(request):
    logout(request)
    messages.info(request, "Session logged out.")
    return redirect('home')