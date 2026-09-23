from django.urls import path
from . import views

urlpatterns = [
    # Storefront & Catalog (Dual zero-arg and positional resolution)
    path('', views.home, name='home'),
    path('catalog/', views.home, name='catalog'),
    path('product/', views.product_details, name='product_details'),
    path('product/<int:pk>/', views.product_details, name='product_details'),
    path('product-details/', views.product_details, name='product_detail'),
    path('product-details/<int:pk>/', views.product_details, name='product_detail'),
    path('category/<str:category_name>/', views.category_view, name='category_view'),
    path('splash/', views.splash, name='splash'),
    path('splash-page/', views.splash, name='splash_page'),

    # Cart Operations (Dual zero-arg and positional resolution)
    path('cart/', views.cart_view, name='cart'),
    path('cart/view/', views.cart_view, name='cart_view'),
    path('cart/page/', views.cart_view, name='cart_page'),
    path('cart/add/', views.add_to_cart, name='add_to_cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.update_cart_quantity, name='update_cart_quantity'),
    path('cart/update/<int:item_id>/', views.update_cart_quantity, name='update_cart_quantity'),
    path('cart/remove/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),

    # Transaction Pipeline
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/page/', views.checkout_view, name='checkout_page'),
    path('order-confirmation/', views.order_confirmation_view, name='order_confirmation'),
    path('order-confirmation/<str:order_number>/', views.order_confirmation_view, name='order_confirmation'),
    path('order-confirmation-default/', views.order_confirmation_view, name='order_confirmation_default'),
    path('order-confirmation-page/<str:order_number>/', views.order_confirmation_view, name='order_confirmation_page'),
    path('orders/', views.orders_history_view, name='orders'),
    path('orders/history/', views.orders_history_view, name='orders_page'),
    path('orders/all/', views.orders_history_view, name='orders_history'),

    # Wishlist & Client-Side AJAX Endpoints
    path('wishlist/', views.wishlist_view, name='wishlist_page'),
    path('wishlist/my-list/', views.wishlist_view, name='wishlist'),
    path('wishlist/view/', views.wishlist_view, name='wishlist_view'),
    path('wishlist/data/', views.wishlist_data, name='wishlist_data'),
    path('wishlist/toggle/', views.toggle_wishlist, name='toggle_wishlist'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('wishlist/add/<int:product_id>/', views.toggle_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:product_id>/', views.toggle_wishlist, name='remove_from_wishlist'),

    # Shipping Destinations
    path('addresses/', views.addresses_view, name='addresses'),
    path('addresses/manage/', views.addresses_view, name='addresses_page'),
    path('address-book/', views.addresses_view, name='address_book'),

    # Identity Management
    path('account/', views.account_hub, name='account_hub'),
    path('account/profile/', views.account_hub, name='account'),
    path('account/hub/', views.account_hub, name='account_page'),
    path('login/', views.login_view, name='login'),
    path('login/page/', views.login_view, name='login_page'),
    path('signup/', views.signup_view, name='signup'),
    path('signup/page/', views.signup_view, name='signup_page'),
    path('logout/', views.logout_view, name='logout'),
]