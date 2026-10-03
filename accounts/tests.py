from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Cart,
    CartItem,
    CompetitorPrice,
    Order,
    OrderItem,
    Product,
    UserProfile,
    Wishlist,
    WishlistItem,
)
from accounts.services import fetch_live_market_radar


class ElectroCartSystemTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Seed verified test user
        self.user = User.objects.create_user(
            username='atelier_tester',
            email='tester@atelier.in',
            password='TestPassword123!'
        )

        self.other_user = User.objects.create_user(
            username='other_patron',
            email='other@atelier.in',
            password='OtherPassword123!'
        )

        # 2. Seed test products calibrated to INR
        self.laptop = Product.objects.create(
            name='MacBook Pro Test Specimen',
            product_code='API-78',
            brand='Apple',
            category='Laptops',
            price=Decimal('175999.00'),
            mrp=Decimal('199999.00'),
            stock=5,
            is_featured=True
        )
        self.accessory = Product.objects.create(
            name='GaN 120W Fast Charger',
            product_code='API-104',
            brand='ElectroCart Labs',
            category='Chargers',
            price=Decimal('2499.00'),
            mrp=Decimal('3499.00'),
            stock=10,
            is_featured=False
        )

    # -------------------------------------------------------------
    # 1. Public Storefront & Routing Verification
    # -------------------------------------------------------------
    def test_public_storefront_loads_without_auth(self):
        """Verifies root (/) loads publicly with HTTP 200 without redirecting to login."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'MacBook Pro Test Specimen')
        self.assertContains(response, '175999.00')

    def test_dual_product_detail_resolution(self):
        """Verifies PDP resolves via both path (/product/1/) and query parameter (/product/?id=1)."""
        res_path = self.client.get(reverse('product_details', kwargs={'pk': self.laptop.pk}))
        self.assertEqual(res_path.status_code, 200)
        self.assertContains(res_path, 'MacBook Pro Test Specimen')

        res_query = self.client.get(f"{reverse('product_details')}?id={self.laptop.pk}")
        self.assertEqual(res_query.status_code, 200)
        self.assertContains(res_query, 'MacBook Pro Test Specimen')

    # -------------------------------------------------------------
    # 2. POST-Only Semantics & State Mutation Security
    # -------------------------------------------------------------
    def test_add_to_cart_rejects_get_and_requires_post(self):
        """Verifies add_to_cart rejects GET requests with 405 Method Not Allowed."""
        get_res = self.client.get(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(get_res.status_code, 405)

    def test_anonymous_guest_can_add_to_cart(self):
        """Verifies unauthenticated visitors obtain a session-backed cart via POST."""
        response = self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})
        self.assertEqual(response.status_code, 302)

        guest_cart = Cart.objects.filter(user__isnull=True).first()
        self.assertIsNotNone(guest_cart)
        self.assertEqual(guest_cart.total_items, 1)
        self.assertEqual(guest_cart.total_price, Decimal('175999.00'))

    def test_add_to_cart_stock_boundary_enforcement(self):
        """Verifies adding quantity exceeding available stock caps to available stock."""
        response = self.client.post(
            reverse('add_to_cart', kwargs={'product_id': self.laptop.id}),
            {'quantity': 99}
        )
        self.assertEqual(response.status_code, 302)
        guest_cart = Cart.objects.filter(user__isnull=True).first()
        self.assertEqual(guest_cart.items.first().quantity, 5)

    # -------------------------------------------------------------
    # 3. Post-Login Cart Reconciliation (Signal Merge)
    # -------------------------------------------------------------
    def test_guest_cart_merges_to_user_on_login(self):
        """Verifies guest cart lines transfer to permanent user cart upon login without duplication."""
        # Step A: Add item as guest via POST
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})
        guest_cart = Cart.objects.filter(user__isnull=True).first()
        self.assertIsNotNone(guest_cart)
        self.assertEqual(guest_cart.total_items, 1)

        # Step B: Authenticate via POST to login view
        login_res = self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })
        self.assertEqual(login_res.status_code, 302)

        # Step C: Assert guest cart is deleted and user cart holds item
        self.assertFalse(Cart.objects.filter(user__isnull=True).exists())
        user_cart = Cart.objects.get(user=self.user)
        self.assertEqual(user_cart.total_items, 1)
        self.assertEqual(user_cart.items.first().product, self.laptop)

    # -------------------------------------------------------------
    # 4. Atomic Concurrency & Negative Inventory Protection
    # -------------------------------------------------------------
    def test_atomic_checkout_deducts_stock_and_creates_invoice(self):
        """Verifies atomic checkout decrements product stock and instantiates Order & OrderItem rows."""
        self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})

        checkout_payload = {
            'name': 'Adarsh Patel',
            'email': 'adarsh@atelier.in',
            'address': '402 Hardware Labs, C.G. Road',
            'city': 'Ahmedabad',
            'state': 'Gujarat',
            'pincode': '380009',
            'phone': '9876543210',
            'payment_method': 'DIRECT_ATELIER'
        }

        initial_stock = self.laptop.stock
        response = self.client.post(reverse('checkout'), checkout_payload)
        self.assertEqual(response.status_code, 302)

        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.stock, initial_stock - 1)

        latest_order = Order.objects.filter(user=self.user).first()
        self.assertIsNotNone(latest_order)
        self.assertEqual(latest_order.total_amount, Decimal('175999.00'))
        self.assertEqual(latest_order.customer_name, 'Adarsh Patel')
        self.assertEqual(latest_order.customer_email, 'adarsh@atelier.in')
        self.assertEqual(latest_order.items.count(), 1)
        self.assertEqual(latest_order.city, 'Ahmedabad')

    def test_checkout_validation_rejects_fake_or_invalid_data(self):
        """Verifies server-side validation rejects invalid email, pincode, or phone."""
        self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})

        bad_payload = {
            'name': '',
            'email': 'not-an-email',
            'address': 'Hi',
            'city': '',
            'state': '',
            'pincode': '12345',
            'phone': '123',
            'payment_method': 'DIRECT_ATELIER'
        }

        response = self.client.post(reverse('checkout'), bad_payload)
        self.assertEqual(response.status_code, 200)
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.stock, 5)
        self.assertEqual(Order.objects.count(), 0)

    def test_atomic_checkout_rolls_back_if_stock_insufficient(self):
        """Verifies if one item has insufficient stock during checkout, the transaction rolls back cleanly."""
        self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.accessory.id}), {'quantity': 1})

        # Artificially deplete laptop stock before submission
        self.laptop.stock = 0
        self.laptop.save()

        initial_accessory_stock = self.accessory.stock

        checkout_payload = {
            'name': 'Adarsh Patel',
            'email': 'adarsh@atelier.in',
            'address': '402 Hardware Labs, C.G. Road',
            'city': 'Ahmedabad',
            'state': 'Gujarat',
            'pincode': '380009',
            'phone': '9876543210',
            'payment_method': 'DIRECT_ATELIER'
        }

        response = self.client.post(reverse('checkout'), checkout_payload)
        self.assertEqual(response.status_code, 200)

        # Accessory stock must NOT have been decremented
        self.accessory.refresh_from_db()
        self.assertEqual(self.accessory.stock, initial_accessory_stock)
        self.assertEqual(Order.objects.count(), 0)

    # -------------------------------------------------------------
    # 5. Order Privacy & Access Control
    # -------------------------------------------------------------
    def test_unauthorized_user_cannot_view_another_users_invoice(self):
        """Verifies users cannot access or view orders belonging to another user."""
        order = Order.objects.create(
            user=self.user,
            order_number='EC-PRIVATE123',
            total_amount=Decimal('175999.00'),
            shipping_address='Private Address',
            city='Ahmedabad',
            state='Gujarat',
            pincode='380009',
            phone='9876543210'
        )

        # Login as a different user
        self.client.post(reverse('login'), {
            'username': 'other_patron',
            'password': 'OtherPassword123!'
        })

        response = self.client.get(reverse('order_confirmation', kwargs={'order_number': order.order_number}))
        self.assertEqual(response.status_code, 302)

    # -------------------------------------------------------------
    # 6. Catalog Search & Filter Functionality
    # -------------------------------------------------------------
    def test_catalog_search_filters_by_name_and_brand(self):
        """Verifies catalog search query parameter ?q= filters products correctly."""
        res = self.client.get(reverse('home') + '?q=MacBook')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'MacBook Pro Test Specimen')
        self.assertNotContains(res, 'GaN 120W Fast Charger')

    def test_catalog_category_filtering(self):
        """Verifies catalog category filter ?category= isolates category products."""
        res = self.client.get(reverse('home') + '?category=Chargers')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'GaN 120W Fast Charger')
        self.assertNotContains(res, 'MacBook Pro Test Specimen')

    # -------------------------------------------------------------
    # 7. Wishlist Authorization & Toggle
    # -------------------------------------------------------------
    def test_unauthenticated_wishlist_toggle_redirects(self):
        """Verifies anonymous wishlist toggle redirects to login."""
        response = self.client.post(reverse('toggle_wishlist', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_authenticated_wishlist_toggle(self):
        """Verifies authenticated user can add and remove items from wishlist."""
        self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })

        # Add to wishlist
        add_res = self.client.post(reverse('toggle_wishlist', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(add_res.status_code, 302)
        wishlist = Wishlist.objects.get(user=self.user)
        self.assertTrue(wishlist.items.filter(product=self.laptop).exists())

        # Toggle again to remove
        del_res = self.client.post(reverse('toggle_wishlist', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(wishlist.items.filter(product=self.laptop).exists())

    # -------------------------------------------------------------
    # 8. Cart Line Operations (Quantity & Removal)
    # -------------------------------------------------------------
    def test_cart_quantity_update_and_removal(self):
        """Verifies increasing, decreasing, and removing line items from cart."""
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})
        guest_cart = Cart.objects.filter(user__isnull=True).first()
        item = guest_cart.items.first()

        # Increase quantity
        self.client.post(reverse('update_cart_quantity', kwargs={'item_id': item.id}), {'action': 'increase'})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        # Remove item
        self.client.post(reverse('remove_from_cart', kwargs={'item_id': item.id}))
        self.assertEqual(guest_cart.items.count(), 0)

    # -------------------------------------------------------------
    # 9. SerpApi 48-Hour Cache Guard Verification
    # -------------------------------------------------------------
    def test_serpapi_local_cache_preserves_quota(self):
        """Verifies fetch_live_market_radar serves cached DB records if younger than 48 hours."""
        CompetitorPrice.objects.create(
            product=self.laptop,
            merchant_name="Amazon India Benchmark",
            price=Decimal('182990.00'),
            product_url="https://www.amazon.in",
            extracted_at=timezone.now() - timedelta(hours=12)
        )

        benchmarks = fetch_live_market_radar(self.laptop)
        self.assertEqual(benchmarks.count(), 1)
        self.assertEqual(benchmarks.first().merchant_name, "Amazon India Benchmark")

    # -------------------------------------------------------------
    # 10. Additional POST-Only Security & State Mutation Guards
    # -------------------------------------------------------------
    def test_post_only_semantics_for_cart_and_wishlist_mutations(self):
        """Verifies cart quantity updates, item removals, and wishlist toggles reject GET with 405."""
        self.client.post(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}), {'quantity': 1})
        guest_cart = Cart.objects.filter(user__isnull=True).first()
        item = guest_cart.items.first()

        res_update_get = self.client.get(reverse('update_cart_quantity', kwargs={'item_id': item.id}))
        self.assertEqual(res_update_get.status_code, 405)

        res_remove_get = self.client.get(reverse('remove_from_cart', kwargs={'item_id': item.id}))
        self.assertEqual(res_remove_get.status_code, 405)

        res_wishlist_get = self.client.get(reverse('toggle_wishlist', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(res_wishlist_get.status_code, 405)

    # -------------------------------------------------------------
    # 11. Custom Error Pages (404, 500, 403)
    # -------------------------------------------------------------
    def test_custom_error_views_render_successfully(self):
        """Verifies custom 404, 500, and 403 error views render with appropriate status codes."""
        res_404 = self.client.get('/nonexistent-route-for-testing/')
        self.assertEqual(res_404.status_code, 404)
        self.assertContains(res_404, '404', status_code=404)

        from accounts.views import custom_500_view, custom_403_view
        from django.test import RequestFactory
        factory = RequestFactory()

        req_500 = factory.get('/')
        res_500 = custom_500_view(req_500)
        self.assertEqual(res_500.status_code, 500)

        req_403 = factory.get('/')
        res_403 = custom_403_view(req_403)
        self.assertEqual(res_403.status_code, 403)

    # -------------------------------------------------------------
    # 12. User Signup & Account Creation Security
    # -------------------------------------------------------------
    def test_signup_creates_user_and_authenticates(self):
        """Verifies public registration creates User, hashes password, and auto-authenticates."""
        signup_payload = {
            'username': 'new_artisan',
            'email': 'artisan@atelier.in',
            'phone': '9876543210',
            'password': 'SecurePassword2026!',
            'confirm_password': 'SecurePassword2026!'
        }
        response = self.client.post(reverse('signup'), signup_payload)
        self.assertEqual(response.status_code, 302)

        created_user = User.objects.filter(username='new_artisan').first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.email, 'artisan@atelier.in')
        self.assertTrue(created_user.check_password('SecurePassword2026!'))
        self.assertEqual(created_user.profile.phone, '9876543210')

    def test_signup_rejects_password_mismatch(self):
        """Verifies signup rejects when password and confirmation differ."""
        bad_payload = {
            'username': 'mismatch_user',
            'email': 'mismatch@atelier.in',
            'password': 'PasswordOne123!',
            'confirm_password': 'PasswordTwo456!'
        }
        response = self.client.post(reverse('signup'), bad_payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='mismatch_user').exists())