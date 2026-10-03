import uuid
import json
import re
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseNotAllowed
from django.utils.http import url_has_allowed_host_and_scheme
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
from .forms import CheckoutForm, SignUpForm, AddressUpdateForm
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
    """
    Master Catalog view with search, category filtering, price filtering,
    stock filtering, and sorting without mandatory login.
    """
    queryset = Product.objects.all()

    # Search query
    q = request.GET.get('q', '').strip()
    if q:
        queryset = queryset.filter(
            Q(name__icontains=q) |
            Q(brand__icontains=q) |
            Q(category__icontains=q) |
            Q(product_code__icontains=q) |
            Q(description__icontains=q)
        )

    # Category filter
    category = request.GET.get('category', '').strip()
    if category:
        queryset = queryset.filter(category__iexact=category)

    # In-stock filter
    in_stock = request.GET.get('in_stock', '').strip()
    if in_stock in ('1', 'true', 'True'):
        queryset = queryset.filter(stock__gt=0)

    # Price range
    min_price = request.GET.get('min_price', '').strip()
    max_price = request.GET.get('max_price', '').strip()
    if min_price:
        try:
            queryset = queryset.filter(price__gte=Decimal(min_price))
        except Exception:
            pass
    if max_price:
        try:
            queryset = queryset.filter(price__lte=Decimal(max_price))
        except Exception:
            pass

    # Sorting
    sort = request.GET.get('sort', '').strip()
    if sort == 'price_asc':
        queryset = queryset.order_by('price')
    elif sort == 'price_desc':
        queryset = queryset.order_by('-price')
    elif sort == 'rating':
        queryset = queryset.order_by('-rating', '-created_at')
    elif sort == 'discount':
        queryset = queryset.order_by('-discount_percentage', '-created_at')
    else:
        queryset = queryset.order_by('-created_at')

    featured_products = Product.objects.filter(is_featured=True)[:6]
    categories = Product.objects.values_list('category', flat=True).distinct().order_by('category')
    cart = get_or_create_cart(request)

    context = {
        'featured_products': featured_products,
        'products': queryset,
        'categories': categories,
        'cart_count': cart.total_items,
        'current_category': category,
        'query': q,
        'current_sort': sort,
        'in_stock_only': in_stock in ('1', 'true', 'True'),
        'total_count': queryset.count(),
    }
    return render(request, 'accounts/home.html', context)


def category_view(request, category_name):
    """Filters products by category with public access."""
    return redirect(f"/?category={category_name}")


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
    """
    POST-only endpoint: Adds product to cart via URL parameter, POST body, or JSON payload.
    Rejects GET requests with 405 Method Not Allowed.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if not product_id:
        product_id = request.POST.get('product_id') or request.GET.get('product_id')
        if not product_id and request.body:
            try:
                data = json.loads(request.body)
                product_id = data.get('product_id') or data.get('id')
            except Exception:
                pass

    product = get_object_or_404(Product, id=product_id)
    cart = get_or_create_cart(request)

    if product.stock <= 0:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': f'{product.name} is out of stock.'}, status=400)
        messages.error(request, f"{product.name} is out of stock.")
        return redirect(request.META.get('HTTP_REFERER', 'home'))

    try:
        qty_requested = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        qty_requested = 1
    if qty_requested < 1:
        qty_requested = 1

    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if not created:
        new_quantity = cart_item.quantity + qty_requested
        if new_quantity > product.stock:
            cart_item.quantity = product.stock
            cart_item.save(update_fields=['quantity'])
            messages.warning(request, f"Quantity capped to available stock ({product.stock}) for {product.name}.")
        else:
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
            messages.success(request, f"Updated quantity for {product.name}.")
    else:
        if qty_requested > product.stock:
            cart_item.quantity = product.stock
            messages.warning(request, f"Quantity capped to available stock ({product.stock}) for {product.name}.")
        else:
            cart_item.quantity = qty_requested
        cart_item.save()
        messages.success(request, f"Added {product.name} to bag.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'cart_count': cart.total_items,
            'cart_total': str(cart.total_price)
        })

    return redirect(request.META.get('HTTP_REFERER', 'cart_view'))


def update_cart_quantity(request, item_id=None):
    """
    POST-only endpoint: updates item quantity or decreases/increases.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if not item_id:
        item_id = request.POST.get('item_id')

    cart = get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    action = request.POST.get('action')
    qty = request.POST.get('quantity')

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
    elif qty is not None:
        try:
            val = int(qty)
            if val <= 0:
                cart_item.delete()
            else:
                cart_item.quantity = min(val, cart_item.product.stock)
                cart_item.save(update_fields=['quantity'])
        except (ValueError, TypeError):
            pass

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'cart_count': cart.total_items,
            'cart_total': str(cart.total_price),
        })

    return redirect('cart_view')


def remove_from_cart(request, item_id=None):
    """
    POST-only endpoint: removes item from cart.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if not item_id:
        item_id = request.POST.get('item_id')

    cart = get_or_create_cart(request)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    cart_item.delete()
    messages.info(request, "Item removed from bag.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'cart_count': cart.total_items,
            'cart_total': str(cart.total_price),
        })

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
    """
    POST-only endpoint: toggles product in authenticated user's wishlist.
    Rejects anonymous users with 401 (AJAX) or redirect to login.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if not request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'auth_required', 'redirect_url': '/login/'}, status=401)
        messages.info(request, "Please sign in to manage your saved collection.")
        return redirect('login')

    if not product_id:
        product_id = request.POST.get('product_id')
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

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
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
        form = AddressUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Delivery parameters updated.")
            return redirect('addresses')
        else:
            messages.error(request, "Please correct the errors in the address form.")
    else:
        form = AddressUpdateForm(instance=profile)

    context = {
        'profile': profile,
        'form': form,
        'cart_count': cart.total_items,
    }
    return render(request, 'accounts/addresses.html', context)


def checkout_view(request):
    """
    Frictionless Checkout: Allows both authenticated users AND guest visitors to checkout.
    Uses CheckoutForm with strict server-side validation and atomic inventory locking.
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
        form = CheckoutForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please correct the errors in the delivery dossier below.")
            return render(request, 'accounts/checkout.html', {
                'cart': cart,
                'items': items,
                'profile': profile,
                'form': form,
                'total_price': cart.total_price
            }, status=200)

        insufficient_product_name = ""
        insufficient_remaining = 0

        try:
            with transaction.atomic():
                # Concurrency safety & inventory locking under select_for_update
                for item in items:
                    locked_product = Product.objects.select_for_update().get(id=item.product.id)
                    if locked_product.stock < item.quantity:
                        insufficient_product_name = locked_product.name
                        insufficient_remaining = locked_product.stock
                        raise ValueError(f"Insufficient stock for {locked_product.name}")

                # Decrement locked inventory atomically
                for item in items:
                    locked_product = Product.objects.select_for_update().get(id=item.product.id)
                    locked_product.stock -= item.quantity
                    locked_product.save(update_fields=['stock'])

                order_num = f"EC-{uuid.uuid4().hex[:8].upper()}"
                order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    customer_name=form.cleaned_data['name'],
                    customer_email=form.cleaned_data['email'],
                    order_number=order_num,
                    total_amount=cart.total_price,
                    shipping_address=form.cleaned_data['address'],
                    city=form.cleaned_data['city'],
                    state=form.cleaned_data['state'],
                    pincode=form.cleaned_data['pincode'],
                    phone=form.cleaned_data['phone'],
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

                if profile:
                    profile.phone = form.cleaned_data['phone']
                    profile.address = form.cleaned_data['address']
                    profile.city = form.cleaned_data['city']
                    profile.state = form.cleaned_data['state']
                    profile.pincode = form.cleaned_data['pincode']
                    profile.save()

                request.session['last_order_number'] = order.order_number
                request.session['guest_customer_name'] = order.customer_name
                request.session['guest_customer_email'] = order.customer_email

                # Clear cart lines
                items.delete()

        except ValueError:
            # Transaction automatically rolled back when ValueError was raised inside atomic block
            messages.error(request, f"Insufficient stock for {insufficient_product_name}. Available: {insufficient_remaining}.")
            return render(request, 'accounts/checkout.html', {
                'cart': cart,
                'items': items,
                'profile': profile,
                'form': form,
                'total_price': cart.total_price
            }, status=200)

        messages.success(request, f"Order #{order.order_number} confirmed successfully.")
        return redirect('order_confirmation', order_number=order.order_number)

    # GET request: initialize form with profile or session data
    initial_data = {}
    if request.user.is_authenticated:
        initial_data['name'] = request.user.get_full_name() or request.user.username
        initial_data['email'] = request.user.email
        if profile:
            initial_data['address'] = profile.address
            initial_data['city'] = profile.city
            initial_data['state'] = profile.state
            initial_data['pincode'] = profile.pincode
            initial_data['phone'] = profile.phone
    else:
        initial_data['name'] = request.session.get('guest_customer_name', '')
        initial_data['email'] = request.session.get('guest_customer_email', '')

    form = CheckoutForm(initial=initial_data)

    return render(request, 'accounts/checkout.html', {
        'cart': cart,
        'items': items,
        'profile': profile,
        'form': form,
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

    guest_name = order.customer_name or request.session.get('guest_customer_name', 'Guest Patron')

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

    requested_next = request.GET.get('next') or request.POST.get('next') or ''
    next_url = requested_next if url_has_allowed_host_and_scheme(
        requested_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) else 'home'

    if request.method == 'POST':
        u = (request.POST.get('username') or request.POST.get('identifier') or request.POST.get('email') or '').strip()
        p = (request.POST.get('password') or request.POST.get('access_key') or '').strip()

        user = authenticate(request, username=u, password=p)
        if user is None:
            user_by_email = User.objects.filter(email__iexact=u).first()
            if user_by_email:
                user = authenticate(request, username=user_by_email.username, password=p)

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

    requested_next = request.GET.get('next') or request.POST.get('next') or ''
    next_url = requested_next if url_has_allowed_host_and_scheme(
        requested_next, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) else 'home'

    if request.method == 'POST':
        u = (request.POST.get('username') or request.POST.get('name') or '').strip()
        e = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        p1 = request.POST.get('password', '').strip()
        p2 = request.POST.get('confirm_password', '').strip()

        if not u and e:
            u = e.split('@')[0]

        if not u or not e or not p1:
            messages.error(request, "All required fields must be completed.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        if p1 != p2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        if len(p1) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        # Sanitize username for Django User model
        u = re.sub(r'[^a-zA-Z0-9_.-]', '_', u)
        base_u = u
        counter = 1
        while User.objects.filter(username__iexact=u).exists():
            u = f"{base_u}{counter}"
            counter += 1

        if User.objects.filter(email__iexact=e).exists():
            messages.error(request, "An account with this email address already exists.")
            return render(request, 'accounts/signup.html', {'next': next_url})

        user = User.objects.create_user(username=u, email=e, password=p1)
        if phone:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save(update_fields=['phone'])

        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Account created successfully.")
        return redirect(next_url)

    return render(request, 'accounts/signup.html', {'next': next_url})


def logout_view(request):
    logout(request)
    messages.info(request, "Session logged out.")
    return redirect('home')


def custom_404_view(request, exception=None):
    return render(request, 'accounts/404.html', status=404)


def custom_500_view(request):
    return render(request, 'accounts/500.html', status=500)


def custom_403_view(request, exception=None):
    return render(request, 'accounts/403.html', status=403)