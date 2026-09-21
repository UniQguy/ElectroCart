import requests

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from accounts.models import Product, ProductImage, ProductSpecification


API_CATEGORY_MAP = {
    "laptops": "Laptops",
    "smartphones": "Smartphones",
    "tablets": "Tablets",
    "mobile-accessories": "Mobile Accessories",
}


class Command(BaseCommand):
    help = "Import products from DummyJSON API"

    def handle(self, *args, **kwargs):

        url = "https://dummyjson.com/products?limit=0"

        self.stdout.write("Fetching products from DummyJSON...")

        response = requests.get(url, timeout=20)

        if response.status_code != 200:
            self.stdout.write(
                self.style.ERROR(
                    f"API Error: {response.status_code}"
                )
            )
            return

        data = response.json()
        products = data.get("products", [])

        self.stdout.write(
            f"Found {len(products)} API products."
        )

        imported = 0
        skipped = 0
        images_saved = 0

        allowed_categories = [
            "Smartphones",
            "Laptops",
            "Mobile Accessories",
            "Tablets",
        ]

        for item in products:

            api_category = item.get("category", "")
            category = API_CATEGORY_MAP.get(
                api_category,
                api_category
            )

            if category not in allowed_categories:
                continue

            product_code = f"API-{item['id']}"

            existing_product = Product.objects.filter(
                product_code=product_code
            ).first()

            # Existing API product
            if existing_product:

                existing_product.category = category
                existing_product.api_sku = item.get("sku", "")
                existing_product.brand = item.get("brand", "")
                existing_product.rating = item.get("rating", 0)
                existing_product.discount_percentage = item.get(
                    "discountPercentage", 0
                )

                existing_product.save(
                    update_fields=[
                        "category",
                        "api_sku",
                        "brand",
                        "rating",
                        "discount_percentage",
                    ]
                )

                # Download gallery images
                image_urls = item.get("images", [])

                for index, image_url in enumerate(image_urls):

                    if not image_url:
                        continue

                    filename = f"api_{item['id']}_gallery_{index + 1}.webp"

                    # Avoid duplicate gallery images
                    if ProductImage.objects.filter(
                        product=existing_product,
                        image__endswith=filename
                    ).exists():
                        continue

                    try:
                        image_response = requests.get(
                            image_url,
                            timeout=20
                        )

                        if image_response.status_code == 200:

                            ProductImage.objects.create(
                                product=existing_product,
                                image=ContentFile(
                                    image_response.content,
                                    name=filename
                                )
                            )

                            images_saved += 1

                            self.stdout.write(
                                f"  Gallery image saved: {filename}"
                            )

                    except requests.RequestException as error:

                        self.stdout.write(
                            self.style.WARNING(
                                f"  Gallery image failed: {error}"
                            )
                        )

                # Save product specifications
                specifications = {
                    "Brand": item.get("brand"),
                    "SKU": item.get("sku"),
                    "Rating": item.get("rating"),
                    "Warranty": item.get("warrantyInformation"),
                    "Shipping": item.get("shippingInformation"),
                    "Availability": item.get("availabilityStatus"),
                }

                for spec_name, spec_value in specifications.items():

                    if spec_value is None or spec_value == "":
                        continue

                    ProductSpecification.objects.update_or_create(
                        product=existing_product,
                        name=spec_name,
                        defaults={
                            "value": str(spec_value)
                        }
                    )

                skipped += 1
                continue

            # New product
            price = item.get("price", 0)

            product = Product.objects.create(
                name=item.get("title", "Unnamed Product"),
                product_code=product_code,
                api_sku=item.get("sku", ""),
                brand=item.get("brand", ""),
                rating=item.get("rating", 0),
                discount_percentage=item.get("discountPercentage", 0),
                description=item.get("description", ""),
                price=price,
                mrp=price,
                category=category,
                quantity=item.get("stock", 0),
                is_active=True,
            )

            image_url = item.get("images", [None])[0]

            if image_url:
                try:
                    image_response = requests.get(
                        image_url,
                        timeout=20
                    )

                    if image_response.status_code == 200:

                        filename = f"api_{item['id']}.webp"

                        product.image.save(
                            filename,
                            ContentFile(image_response.content),
                            save=True
                        )

                        images_saved += 1

                        self.stdout.write(
                            f"  Main image saved: {filename}"
                        )

                except requests.RequestException as error:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Image download failed: {error}"
                        )
                    )

            imported += 1

            self.stdout.write(
                f"Imported: {item.get('title')}"
            )

        self.stdout.write("")

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete! "
                f"Imported: {imported} | "
                f"Skipped: {skipped} | "
                f"Images saved: {images_saved}"
            )
        )
