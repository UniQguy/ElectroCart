from .models import Cart, Product, Wishlist


def store_context(request):
    """
    Global context processor providing cart count, wishlist count, and categories
    across all templates cleanly without redundant view queries.
    """
    cart_count = 0
    wishlist_count = 0
    cart = None

    try:
        if request.user.is_authenticated:
            cart = Cart.objects.filter(user=request.user).first()
            if cart:
                cart_count = cart.total_items
            wishlist = Wishlist.objects.filter(user=request.user).first()
            if wishlist:
                wishlist_count = wishlist.items.count()
        else:
            session_key = request.session.session_key
            cart_id = request.session.get('cart_id')
            if cart_id:
                cart = Cart.objects.filter(id=cart_id, user__isnull=True).first()
            elif session_key:
                cart = Cart.objects.filter(session_key=session_key, user__isnull=True).first()

            if cart:
                cart_count = cart.total_items
    except Exception:
        # Failsafe during migrations or edge cases
        pass

    try:
        categories = list(Product.objects.values_list('category', flat=True).distinct().order_by('category'))
    except Exception:
        categories = []

    return {
        'cart_count': cart_count,
        'wishlist_count': wishlist_count,
        'store_categories': categories,
        'active_cart': cart,
    }

