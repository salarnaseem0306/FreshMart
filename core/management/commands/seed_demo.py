from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from catalog.models import Category, Product
from inventory.models import StockMovement, Supplier
from inventory.services import change_stock

PASSWORD = "freshmart123"

SUPPLIERS = [
    ("Fresh Farms Ltd", "0300-1111111", "orders@freshfarms.example"),
    ("City Bakery Supply", "0300-2222222", "sales@citybakery.example"),
    ("Metro Wholesale", "0300-3333333", "trade@metro.example"),
]

CATALOG = {
    "Dairy": [
        ("Fresh Milk 1L", "2.50"), ("Yogurt 500g", "1.80"), ("Cheddar Cheese 200g", "3.90"),
        ("Butter 250g", "3.20"), ("Eggs Dozen", "3.00"), ("Cream 200ml", "1.60"),
        ("Cottage Cheese 250g", "2.40"), ("Mozzarella 250g", "3.70"),
    ],
    "Bakery": [
        ("White Bread", "1.20"), ("Brown Bread", "1.50"), ("Croissant", "0.90"),
        ("Bagels 4-pack", "2.20"), ("Baguette", "1.10"), ("Muffin", "1.30"),
        ("Pita Bread 6-pack", "1.70"), ("Cinnamon Roll", "1.40"),
    ],
    "Beverages": [
        ("Orange Juice 1L", "2.90"), ("Cola 1.5L", "1.60"), ("Mineral Water 1.5L", "0.80"),
        ("Green Tea 20 bags", "2.60"), ("Coffee Beans 250g", "6.50"), ("Apple Juice 1L", "2.70"),
        ("Energy Drink 250ml", "1.90"), ("Iced Tea 500ml", "1.40"),
    ],
    "Produce": [
        ("Bananas 1kg", "1.40"), ("Apples 1kg", "2.80"), ("Tomatoes 1kg", "2.10"),
        ("Potatoes 2kg", "2.60"), ("Onions 1kg", "1.30"), ("Carrots 1kg", "1.50"),
        ("Cucumber", "0.60"), ("Lemons 500g", "1.90"),
    ],
    "Snacks": [
        ("Potato Chips 150g", "1.80"), ("Salted Peanuts 200g", "2.30"), ("Chocolate Bar 100g", "1.50"),
        ("Cookies 300g", "2.40"), ("Popcorn 100g", "1.60"), ("Crackers 200g", "1.70"),
        ("Granola Bar 5-pack", "3.10"), ("Dark Chocolate 100g", "2.20"),
    ],
}


class Command(BaseCommand):
    help = "Create demo users, categories, suppliers and products (safe to run twice)."

    @transaction.atomic
    def handle(self, *args, **options):
        manager = self._users()
        suppliers = [
            Supplier.objects.get_or_create(
                name=name, defaults={"phone": phone, "email": email}
            )[0]
            for name, phone, email in SUPPLIERS
        ]

        created_products = 0
        index = 0
        for cat_no, (cat_name, items) in enumerate(CATALOG.items()):
            category, _ = Category.objects.get_or_create(name=cat_name)
            supplier = suppliers[cat_no % len(suppliers)]
            for name, price in items:
                index += 1
                sku = f"{cat_name[:3].upper()}-{index:03d}"
                product, created = Product.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "name": name,
                        "barcode": f"890{index:010d}",
                        "category": category,
                        "price": Decimal(price),
                    },
                )
                if created:
                    created_products += 1
                    qty = 4 if index % 9 == 0 else 5 + (index * 11) % 70
                    self._receive(product, qty, supplier, manager)

        self.stdout.write(self.style.SUCCESS(
            f"Done. New products this run: {created_products}. "
            f"Total products: {Product.objects.count()}."
        ))

    def _users(self):
        manager = None
        for username, role in [
            ("manager1", User.Role.MANAGER),
            ("cashier1", User.Role.CASHIER),
            ("cashier2", User.Role.CASHIER),
        ]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "email": f"{username}@freshmart.example",
                    "is_staff": role == User.Role.MANAGER,
                },
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            if username == "manager1":
                manager = user
        return manager

    def _receive(self, product, qty, supplier, user):
        # Opening stock is a purchase movement made through the one allowed door.
        change_stock(
            product, qty, StockMovement.Reason.PURCHASE, user,
            supplier=supplier, note="Opening stock",
        )