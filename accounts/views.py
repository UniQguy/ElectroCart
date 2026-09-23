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
)
from .services import fetch_live_market_radar


def splash(request):
    return redirect('home')


def get_or_create_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    if not request.session.session_key:
        request.session.create()

    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key)
    return cart


def home(request):
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

    # Market Radar Benchmark Calculation
    market_benchmark = fetch_live_market_radar(product)
    lowest_competitor = market_benchmark.first() if market_benchmark else None
    savings_vs_market = None
    if lowest_competitor and lowest_competitor.price > product.price:
        savings_vs_market = lowest_competitor.price - product.price

    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = WishlistItem.objects.filter(wishlist__user=request.user, product=product).exists()

    context = {
        'product': product,
        'gallery': gallery,
        'specs': specs,
        'cart_count': cart.total_items,
        'in_wishlist': in_wishlist,
        'market_benchmark': market_benchmark,
        'lowest_competitor': lowest_competitor,
        'savings_vs_market': savings_vs_market,
    }
    return render(request, 'accounts/product_details.html', context)


def cart_view(request):
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
    if not product_id:
        product_id = request.POST.get('product_id') or request.GET.get('product_id') or request.GET.get('id')
        if not product_id and request.body:
            try:
                data = json.loads(request.body)
                product_id = data.get('product_id') or data.get('id')
            except Exception:
                pass

    if not product_id:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'No product specified.'}, status=400)
        messages.error(request, "No product specified.")
        return redirect('home')

    product = get_object_or_404(Product, id=product_id)
    cart = get_or_create_cart(request)

    if product.stock <= 0:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': f'{product.name} is out of stock.'}, status=400)
        messages.error(request, f"{product.name} is out of stock.")
        return redirect(request.META.get('HTTP_REFERER', 'home'))

    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        if cart_item.quantity < product.stock:
            cart_item.quantity += 1
            cart_item.save(update_fields=['quantity'])
            msg = f"Updated quantity for {product.name}."
        else:
            msg = f"Maximum available stock is {product.stock} units."
    else:
        msg = f"Added {product.name} to bag."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message': msg,
            'cart_count': cart.total_items,
            'cart_total': str(cart.total_price),
            'product_name': product.name
        })

    messages.success(request, msg)
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
        messages.info(request, "Please sign in to manage your collection.")
        return redirect('login')

    if not product_id:
        product_id = request.POST.get('product_id') or request.GET.get('product_id')
        if not product_id and request.body:
            try:
                data = json.loads(request.body)
                product_id = data.get('product_id') or data.get('id')
            except Exception:
                pass

    if not product_id:
        return JsonResponse({'status': 'error', 'message': 'No product specified.'}, status=400)

    product = get_object_or_404(Product, id=product_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    existing_item = wishlist.items.filter(product=product).first()

    if existing_item:
        existing_item.delete()
        is_saved = False
        messages.info(request, f"Removed {product.name} from collection.")
    else:
        WishlistItem.objects.create(wishlist=wishlist, product=product)
        is_saved = True
        messages.success(request, f"Saved {product.name} to collection.")

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
        messages.success(request, "Delivery address updated.")
        return redirect('addresses')

    context = {
        'profile': profile,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/addresses.html', context)


@transaction.atomic
def checkout_view(request):
    cart = get_or_create_cart(request)
    items = cart.items.select_related('product').all()

    if not items.exists():
        messages.warning(request, "Your bag is empty.")
        return redirect('home')

    if not request.user.is_authenticated:
        return redirect('/login/?next=/checkout/')

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        address = (request.POST.get('address') or request.POST.get('shipping_address') or profile.address or 'Standard Delivery Address').strip()
        city = (request.POST.get('city') or profile.city or 'Ahmedabad').strip()
        state = (request.POST.get('state') or profile.state or 'Gujarat').strip()
        pincode = (request.POST.get('pincode') or request.POST.get('zip_code') or profile.pincode or '380009').strip()
        phone = (request.POST.get('phone') or request.POST.get('contact_number') or profile.phone or '9999999999').strip()

        profile.address = address
        profile.city = city
        profile.state = state
        profile.pincode = pincode
        profile.phone = phone
        profile.save()

        for item in items:
            locked_product = Product.objects.select_for_update().get(id=item.product.id)
            if locked_product.stock < item.quantity:
                messages.error(request, f"Insufficient stock for {locked_product.name}. Remaining: {locked_product.stock}.")
                return render(request, 'accounts/checkout.html', {
                    'cart': cart,
                    'items': items,
                    'profile': profile,
                    'total_price': cart.total_price,
                    'cart_count': cart.total_items,
                })

            locked_product.stock -= item.quantity
            locked_product.save(update_fields=['stock'])

        order_num = f"EC-{uuid.uuid4().hex[:8].upper()}"
        order = Order.objects.create(
            user=request.user,
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

        items.delete()
        request.session['last_order_number'] = order.order_number
        return redirect('order_confirmation', order_number=order.order_number)

    return render(request, 'accounts/checkout.html', {
        'cart': cart,
        'items': items,
        'profile': profile,
        'total_price': cart.total_price,
        'cart_count': cart.total_items,
    })


def order_confirmation_view(request, order_number=None):
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

    if request.user.is_authenticated and order.user != request.user and not request.user.is_staff:
        messages.error(request, "Access unauthorized for this order invoice.")
        return redirect('home')

    context = {
        'order': order,
        'order_items': order.items.all(),
        'subtotal': order.total_amount,
        'cart_count': 0,
    }
    return render(request, 'accounts/order_confirmation.html', context)


@login_required
def orders_history_view(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product')
    cart = get_or_create_cart(request)
    return render(request, 'accounts/orders.html', {
        'orders': orders,
        'cart_count': cart.total_items,
    })


@login_required
def account_hub(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    recent_orders = Order.objects.filter(user=request.user)[:3]
    cart = get_or_create_cart(request)
    return render(request, 'accounts/account_hub.html', {
        'profile': profile,
        'recent_orders': recent_orders,
        'cart_count': cart.total_items,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    next_url = request.GET.get('next') or request.POST.get('next') or 'home'

    if request.method == 'POST':
        u = request.POST.get('username', '').strip()
        p = request.POST.get('password', '').strip()
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            messages.success(request, f"Authenticated as {user.username}.")
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")

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