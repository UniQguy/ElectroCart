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
        # Path parameter resolution
        res_path = self.client.get(reverse('product_details', kwargs={'pk': self.laptop.pk}))
        self.assertEqual(res_path.status_code, 200)
        self.assertContains(res_path, 'MacBook Pro Test Specimen')

        # Query parameter resolution (?id=...)
        res_query = self.client.get(f"{reverse('product_details')}?id={self.laptop.pk}")
        self.assertEqual(res_query.status_code, 200)
        self.assertContains(res_query, 'MacBook Pro Test Specimen')

    # -------------------------------------------------------------
    # 2. Guest Session Cart Operations
    # -------------------------------------------------------------
    def test_anonymous_guest_can_add_to_cart(self):
        """Verifies unauthenticated visitors obtain a session-backed cart."""
        response = self.client.get(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}))
        self.assertEqual(response.status_code, 302)

        guest_cart = Cart.objects.filter(user__isnull=True).first()
        self.assertIsNotNone(guest_cart)
        self.assertEqual(guest_cart.total_items, 1)
        self.assertEqual(guest_cart.total_price, Decimal('175999.00'))

    # -------------------------------------------------------------
    # 3. Post-Login Cart Reconciliation (Signal Merge)
    # -------------------------------------------------------------
    def test_guest_cart_merges_to_user_on_login(self):
        """Verifies guest cart lines transfer to permanent user cart upon login without duplication."""
        # Step A: Add item as guest
        self.client.get(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}))
        guest_cart = Cart.objects.filter(user__isnull=True).first()
        self.assertIsNotNone(guest_cart)
        self.assertEqual(guest_cart.total_items, 1)

        # Step B: Authenticate via POST to login view (real request + session cycle)
        login_res = self.client.post(reverse('login'), {
            'username': 'atelier_tester',
            'password': 'TestPassword123!'
        })
        self.assertEqual(login_res.status_code, 302)

        # Step C: Assert guest cart is deleted and user cart holds the item
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
        self.client.get(reverse('add_to_cart', kwargs={'product_id': self.laptop.id}))

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
        self.assertEqual(latest_order.items.count(), 1)
        self.assertEqual(latest_order.city, 'Ahmedabad')

    # -------------------------------------------------------------
    # 5. SerpApi 48-Hour Cache Guard Verification
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