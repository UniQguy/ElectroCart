import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ElectroCart.settings')
django.setup()

from decimal import Decimal
from accounts.models import Product

def run_price_fix():
    print("Executing currency normalization on API products (USD -> INR @ 88x)...")
    api_products = Product.objects.filter(product_code__startswith='API-')
    updated = 0
    already_done = 0

    for p in api_products:
        raw_price = float(p.price)
        if raw_price < 3500.0:
            scaled_price = round(raw_price * 88.0, 2)
            p.price = Decimal(str(scaled_price))
            
            discount = float(p.discount_percentage or 12.0)
            mrp = round(scaled_price / (1 - (discount / 100.0)), 2)
            p.mrp = Decimal(str(mrp))
            
            p.save(update_fields=['price', 'mrp'])
            updated += 1
            print(f"  [CONVERTED] {p.name} -> Price: INR {p.price:,.2f} | MRP: INR {p.mrp:,.2f}")
        else:
            already_done += 1
            print(f"  [SKIPPED] {p.name} already at INR {p.price:,.2f}")

    print(f"\nDone: {updated} records converted, {already_done} already normalized.")

if __name__ == '__main__':
    run_price_fix()