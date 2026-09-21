from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [

    path("", views.splash, name="splash"),

    path(
        "splash/",
        views.splash,
        name="splash_page"
    ),

    path(
        "login/",
        views.login_user,
        name="login"
    ),

    path(
        "signup/",
        views.signup_user,
        name="signup"
    ),

    path(
        "home/",
        views.home,
        name="home"
    ),


    # PRODUCT
    path(
        "product-details/",
        views.product_details,
        name="product_details"
    ),


    # ACCOUNT
    path(
        "account/",
        views.account_hub,
        name="account_hub"
    ),

    path(
        "account/orders/",
        views.orders,
        name="orders"
    ),

    path(
        "account/wishlist/",
        views.wishlist_page,
        name="wishlist_page"
    ),

    path(
        "account/addresses/",
        views.addresses,
        name="addresses"
    ),


    # CART
    path(
        "cart/",
        views.cart_page,
        name="cart_page"
    ),


    # CHECKOUT
    path(
        "checkout/",
        views.checkout,
        name="checkout"
    ),

    path(
        "api/checkout/validate-stock/",
        views.validate_checkout_stock,
        name="validate_checkout_stock"
    ),


    # CART API
    path(
        "api/cart/add/",
        views.add_to_cart,
        name="add_to_cart"
    ),

    path(
        "api/cart/update/",
        views.update_cart,
        name="update_cart"
    ),

    path(
        "api/cart/",
        views.cart_data,
        name="cart_data"
    ),


    # WISHLIST API
    path(
        "api/wishlist/toggle/",
        views.toggle_wishlist,
        name="toggle_wishlist"
    ),

    path(
        "api/wishlist/",
        views.wishlist_data,
        name="wishlist_data"
    ),


    # ORDER CONFIRMATION
    path(
        "order-confirmation/",
        views.order_confirmation,
        name="order_confirmation"
    ),


    # LOGOUT
    path(
        "logout/",
        views.logout_user,
        name="logout"
    ),
]

urlpatterns += static(
    settings.MEDIA_URL,
    document_root=settings.MEDIA_ROOT
)