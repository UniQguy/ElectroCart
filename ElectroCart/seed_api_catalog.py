import os
import sys
import json
import urllib.request
from decimal import Decimal

# Initialize Django standalone environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ElectroCart.settings')
try:
    import django
    django.setup()
except Exception as e:
    print(f"Error initializing Django: {e}")
    sys.exit(1)

from django.core.files.base import ContentFile
from django.conf import settings
from accounts.models import Product, ProductImage

CATEGORY_MAP = {
    'laptops': 'Laptops',
    'smartphones': 'Smartphones',
    'mobile-accessories': 'Mobile Accessories',
    'tablets': 'Tablets',
}

# Currency Scaling: $1 USD ≈ ₹88.00 INR (Accounts for GST & Indian retail duties)
CURRENCY_MULTIPLIER = 88.0

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))

def run_import():
    print("==================================================")
    print("ELECTROCART — ROBUST CATALOG INGESTION & INR SCALING")
    print("==================================================")
    
    total_created = 0
    total_updated = 0

    for api_cat, local_cat in CATEGORY_MAP.items():
        url = f"https://dummyjson.com/products/category/{api_cat}"
        print(f"\n[Category: {local_cat}] Connecting to {url}...")
        
        try:
            data = fetch_json(url)
        except Exception as err:
            print(f"  [ERROR] Could not fetch category {api_cat}: {err}")
            continue

        products = data.get('products', [])
        for item in products:
            product_code = f"API-{item['id']}"

            # Calculate authentic Indian retail prices
            usd_price = float(item.get('price', 0.0))
            inr_price = round(usd_price * CURRENCY_MULTIPLIER, 2)
            discount = float(item.get('discountPercentage', 12.0))
            inr_mrp = round(inr_price / (1 - (discount / 100.0)), 2)

            product, created = Product.objects.update_or_create(
                product_code=product_code,
                defaults={
                    'name': item.get('title', 'Unknown Product'),
                    'description': item.get('description', ''),
                    'brand': item.get('brand', 'Independent'),
                    'price': Decimal(str(inr_price)),
                    'mrp': Decimal(str(inr_mrp)),
                    'discount_percentage': Decimal(str(round(discount, 2))),
                    'stock': item.get('stock', 15),
                    'category': local_cat,
                    'api_sku': item.get('sku', f"SKU-{item['id']}"),
                    'rating': Decimal(str(round(float(item.get('rating', 4.5)), 2))),
                }
            )

            # Check if local image already exists from partner's commit, otherwise download
            local_img_name = f"api_{item['id']}.webp"
            local_media_path = os.path.join(settings.MEDIA_ROOT, 'products', local_img_name)
            
            if os.path.exists(local_media_path) and not product.image:
                product.image = f"products/{local_img_name}"
                product.save(update_fields=['image'])
            elif not product.image and item.get('thumbnail'):
                try:
                    img_req = urllib.request.Request(item['thumbnail'], headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(img_req, timeout=10) as img_resp:
                        product.image.save(local_img_name, ContentFile(img_resp.read()), save=True)
                except Exception as img_err:
                    print(f"    [WARN] Thumbnail failed for {product_code}: {img_err}")

            # Populate gallery images if missing
            if not product.gallery_images.exists():
                for idx, g_url in enumerate(item.get('images', [])[:4]):
                    g_img_name = f"gallery_api_{item['id']}_{idx}.webp"
                    g_media_path = os.path.join(settings.MEDIA_ROOT, 'products', 'gallery', g_img_name)
                    
                    if os.path.exists(g_media_path):
                        ProductImage.objects.create(
                            product=product,
                            image=f"products/gallery/{g_img_name}",
                            is_primary=(idx == 0)
                        )
                    else:
                        try:
                            g_req = urllib.request.Request(g_url, headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(g_req, timeout=10) as g_resp:
                                p_img = ProductImage(product=product, is_primary=(idx == 0))
                                p_img.image.save(g_img_name, ContentFile(g_resp.read()), save=True)
                        except Exception:
                            continue

            if created:
                total_created += 1
                print(f"  [+] Created: {product.name[:32]} -> ₹{inr_price:,.2f}")
            else:
                total_updated += 1
                print(f"  [~] Synchronized: {product.name[:32]} -> ₹{inr_price:,.2f}")

    total_in_db = Product.objects.count()
    print("\n==================================================")
    print(f"INGESTION COMPLETE")
    print(f"Created: {total_created} | Updated: {total_updated}")
    print(f"Total Products in Database: {total_in_db} (24 Original + {total_created + total_updated} API)")
    print("==================================================")

if __name__ == '__main__':
    run_import()