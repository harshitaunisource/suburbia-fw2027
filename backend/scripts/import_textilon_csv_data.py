"""
One-off: imports the Textilon product data you collected manually via
the "Web Scraper" Chrome extension (7 CSV files + one pasted table)
into the unified `products` table, tagged correctly by category and
gender, under Textilon as a BUYER (not a competitor) -- per your
instruction that Textilon is a buyer, so category-wise organization
matters here specifically.

Data source: the raw rows below were transcribed directly from the
CSV files you uploaded and the table you pasted. Each source file used
a different, inconsistent column layout (the extension exports columns
in whatever order you clicked them in per scraping session) -- these
have already been normalized into one consistent shape per row:
(name, price, original_price, image_url).

Product URLs are RECONSTRUCTED, not literally present in your CSVs --
the extension only captured the category start_url and each product's
image URL, not its individual detail-page URL. Confirmed live earlier
in this project: a real Textilon product URL follows the pattern
https://bo.textilon.com/producto/<code>, and the CSV's own image
filename IS that same product code (e.g. image ".../012C-205.jpg"
-> https://bo.textilon.com/producto/012C-205 -- this exact code/URL
pair was independently confirmed by you pasting that real product link
earlier in this project). So the product code is extracted from each
image filename and used to rebuild the real product URL directly,
rather than being guessed.

Currency: BOB (Bolivianos) -- bo.textilon.com is Textilon's Bolivia
storefront; confirmed live via an earlier screenshot showing a
Textilon product priced "BOB 369".

Safe to re-run: every insert is guarded by product_url, so re-running
this after already importing just does nothing on the second pass.

Usage:
    cd backend
    python -m scripts.import_textilon_csv_data
"""
import re
import uuid
from datetime import datetime

from app.database import SessionLocal
from app.models import Buyer, Gender, GenericSourceConfig, ItemHierarchy, Product, SourceRole

BRAND = "Textilon"
CURRENCY = "BOB"

# (gender, sub_category, real category URL observed in the CSV's own
# web_scraper_start_url column, rows)
# Each row: (name, price, original_price_or_None, image_url)
CATEGORIES = [
    {
        "gender": Gender.WOMENS,
        "sub_category": "Bottoms",
        "category_url": "https://bo.textilon.com/articulos/categoria/mujer/subcategoria/jeans%20y%20leggings",
        "rows": [
            ("WIDE LEG JEAN", 549.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/jeans-y-leggings_500x600/JB014-101.jpg"),
            ("STRAIGHT JEANS", 549.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/jeans-y-leggings_500x600/JB015-101.jpg"),
            ("STRAIGHT JEANS", 549.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/jeans-y-leggings_500x600/JB016-101.jpg"),
            ("THERMAL LEGGINGS", 229.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/jeans-y-leggings_500x600/TL0142.jpg"),
        ],
    },
    {
        "gender": Gender.MENS,
        "sub_category": "Pajamas",
        "category_url": "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/pijamas",
        "rows": [
            ("Men's PJ Shirt Mc Short", 199.50, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC012-201.jpg"),
            ("Men's PJ Shirt Long Sleeve Jogger", 249.50, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC013-201.jpg"),
            ("Men's PJ Shirt Mc Short", 199.50, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC014-201.jpg"),
            ("Men's PJ Shirt Mc Short", 199.50, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC016-201.jpg"),
            ("Men's pajamas: jacket and pants", 349.30, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC043-201.jpg"),
            ("Men's PJ Set: Long Sleeve T-Shirt and Jogger", 349.30, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC044-201.jpg"),
            ("Men's PJ Set: Short Sleeve Shirt and Shorts", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC045-201.jpg"),
            ("Men's PJ Set: Long Sleeve T-Shirt and Jogger", 349.30, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC046-201.jpg"),
            ("Men's PJ Set: Long Sleeve T-Shirt and Jogger", 349.30, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC051-201.jpg"),
            ("Men's PJ Set: Long Sleeve T-Shirt and Jogger", 349.30, 499.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC053-201.jpg"),
            ("PJ Men's Micropolar", 499.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/PB12-201.jpg"),
            ("Men's PJ Set: Short Sleeve Shirt and Shorts", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pijamas_500x600/NVC047-201.jpg"),
        ],
    },
    {
        "gender": Gender.MENS,
        "sub_category": "T shirt",
        "category_url": "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/camisetas",
        "rows": [
            ("Thermal T-Shirt", 49.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/012C-205.jpg"),
            ("Cotton Short Sleeve T-Shirt With Round Neck – Pack of 2 Units", 249.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/013-205-B.jpg"),
            ("Long Sleeve Cotton V-Neck T-Shirt - Pack of 2", 149.50, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/013-207.jpg"),
            ("Long Sleeve Cotton T-Shirt With Round Neck - Pack of 2", 299.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/013-208.jpg"),
            ("Cotton Sleeve T-Shirt – Pack of 2 Units", 199.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/018-202.jpg"),
            ("Slim Fit Short Sleeve V-Neck T-Shirt – Pack of 2 Units", 269.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/2807-101-A.jpg"),
            ("Slim Fit Short Sleeve T-Shirt With Round Neck – Pack of 2 Units", 269.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/2808-101.jpg"),
            ("Slim Fit Sleeveless T-Shirt – Pack of 2 Units", 259.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/2809-101-B.jpg"),
            ("Basic Polo Shirt 100% Cotton", 149.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/OWP01-201_blanca.jpg"),
            ("Cotton Polo Shirt", 299.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/camisetas_500x600/OWPP01-201_negro.jpg"),
        ],
    },
    {
        "gender": Gender.MENS,
        "sub_category": "Joggers & Sweatshirts",
        "category_url": "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/joggers%20y%20sudaderas",
        "rows": [
            ("Zippered Sweatshirt With Pocket", 499.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/joggers-y-sudaderas_500x600/LB008-201_negro.jpg"),
            ("Half-Zip Sweatshirt", 499.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/joggers-y-sudaderas_500x600/LB009-201_negro.jpg"),
            ("Straight Jogger", 449.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/joggers-y-sudaderas_500x600/LB010-201.jpg"),
            ("Straight Jogger", 449.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/joggers-y-sudaderas_500x600/LB017-201.jpg"),
        ],
    },
    {
        "gender": Gender.MENS,
        "sub_category": "Bottoms",
        "category_url": "https://bo.textilon.com/articulos/categoria/hombre/subcategoria/pantalones%20y%20bermudas",
        "rows": [
            ("Bermuda", 174.50, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pantalones-y-bermudas_500x600/BC002-201.jpg"),
            ("Jean Slim", 549.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pantalones-y-bermudas_500x600/JB017-201.jpg"),
            ("Chino Trousers", 499.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pantalones-y-bermudas_500x600/PC001-201.jpg"),
            ("Chino Pants", 399.20, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/HOMBRE/pantalones-y-bermudas_500x600/PC002-201.jpg"),
        ],
    },
    {
        "gender": Gender.KIDS,
        "sub_category": "Pajamas",
        "category_url": "https://bo.textilon.com/articulos/categoria/ni%C3%B1as%20y%20ni%C3%B1os/subcategoria/pijamas",
        "rows": [
            ("Girl's PJ Set: Long-Sleeved T-Shirt and Joggers", 279.30, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/NVC050A-301.jpg"),
            ("PJ Kids Shirt ML and Jogger", 279.30, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/NVC051A-301.jpg"),
            ("Girl's PJ Set: Long-Sleeved T-Shirt and Joggers", 279.30, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/NVC052A-301.jpg"),
            ("PJ Kids Shirt ML and Jogger", 279.30, 399.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/NVC053A-301.jpg"),
            ("Printed Microfleece PJs For Boys", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/PB010-302.jpg"),
            ("Girl's Printed Microfleece PJs", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/PB010-301.jpg"),
            ("Plush Pajamas", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/PB011-301.jpg"),
            ("Plush Pajamas", 399.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/NI%C3%91AS-Y-NI%C3%91OS/pijamas_500x600/PB012-301.jpg"),
        ],
    },
    {
        "gender": Gender.WOMENS,
        "sub_category": "T shirt",
        "category_url": "https://bo.textilon.com/articulos/categoria/mujer/subcategoria/camisetas",
        "rows": [
            ("Short Sleeve Thermal T-Shirt", 24.50, 49.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/011-104.jpg"),
            ("Thermal T-Shirt", 49.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/011C-105.jpg"),
            ("Short Sleeve Thermal T-Shirt", 24.50, 49.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/012-205.jpg"),
            ("Short Sleeve Round Neck T-Shirt - Pack x2", 94.50, 189.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/2013-101-RA.jpg"),
            ("Short Sleeve Round Neck T-Shirt - Pack x2", 94.50, 189.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/2013-101.jpg"),
            ("Slim Leg T-Shirt - Pack of 2 Units", 219.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/778-101.jpg"),
            ("High Neck T-Shirt", 159.20, 199.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/794-102N.jpg"),
            ("Long Sleeve T-Shirt - Pack of 2 Units", 263.20, 329.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/794-103.jpg"),
            ("Slim Fit Long Sleeve T-Shirt Pack x 2 Units", 263.20, 329.00,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/794-202.jpg"),
            ("Basic Polo Shirt 100% Cotton", 149.00, None,
             "https://textilon-store.nyc3.digitaloceanspaces.com/bo/MUJER/camisetas_500x600/OWP01-101_blanca.jpg"),
        ],
    },
]

ITEM_TYPE = "GARMENT"
CATEGORY = "APPAREL"


def _code_from_image_url(image_url: str) -> str:
    """Extracts the product code from the image filename -- e.g.
    '.../012C-205.jpg' -> '012C-205'. This IS the real product code:
    confirmed live earlier via a real Textilon product URL
    (https://bo.textilon.com/producto/012C-205) matching this exact
    pattern for this exact product."""
    filename = image_url.rsplit("/", 1)[-1]
    stem = re.sub(r"\.(jpg|jpeg|png|webp)$", "", filename, flags=re.IGNORECASE)
    return stem


def _product_url_from_code(code: str) -> str:
    # Strip a trailing color-variant suffix (e.g. "_blanca", "_negro")
    # for the URL specifically -- the real product page is keyed by the
    # base code, with color handled as an in-page variant selector, not
    # a separate URL. The full code (with suffix) is still kept as
    # product_code below, so two color variants of the same base style
    # remain distinguishable in the catalogue even though they'd both
    # point at the same underlying product page.
    base_code = code.split("_")[0]
    return f"https://bo.textilon.com/producto/{base_code}"


def get_or_create_hierarchy(db, item_type: str, category: str, sub_category: str) -> ItemHierarchy:
    existing = (
        db.query(ItemHierarchy)
        .filter(
            ItemHierarchy.item_type == item_type,
            ItemHierarchy.category == category,
            ItemHierarchy.sub_category == sub_category,
        )
        .first()
    )
    if existing:
        return existing
    row = ItemHierarchy(item_type=item_type, category=category, sub_category=sub_category)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_or_create_source(
    db, buyer: Buyer, hierarchy: ItemHierarchy, gender: Gender, category_url: str
) -> GenericSourceConfig:
    existing = (
        db.query(GenericSourceConfig)
        .filter(
            GenericSourceConfig.sub_category_id == hierarchy.id,
            GenericSourceConfig.brand.ilike(BRAND),
            GenericSourceConfig.gender == gender,
        )
        .first()
    )
    if existing:
        # If this source was previously created some other way (e.g.
        # via Search Products, which doesn't set a buyer), correct it
        # now that we know for certain Textilon is a buyer -- keeps
        # this consistent with any future re-scrape of the same source.
        changed = False
        if existing.buyer_id != buyer.id:
            existing.buyer_id = buyer.id
            changed = True
        if existing.role != SourceRole.BUYER:
            existing.role = SourceRole.BUYER
            changed = True
        if changed:
            db.commit()
        return existing

    source = GenericSourceConfig(
        sub_category_id=hierarchy.id,
        buyer_id=buyer.id,
        role=SourceRole.BUYER,
        gender=gender,
        brand=BRAND,
        category_url=category_url,
        currency=CURRENCY,
        notes="Imported from manually-collected Chrome extension CSV data (2026-09-07).",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def import_data():
    db = SessionLocal()
    try:
        buyer = db.query(Buyer).filter(Buyer.name.ilike(BRAND)).first()
        if not buyer:
            buyer = Buyer(name=BRAND, notes="Added via manual CSV import (2026-09-07).")
            db.add(buyer)
            db.commit()
            db.refresh(buyer)
            print(f"Created buyer '{BRAND}' (id={buyer.id}).")
        else:
            print(f"Using existing buyer '{BRAND}' (id={buyer.id}).")

        total_inserted = 0
        total_skipped = 0

        for group in CATEGORIES:
            hierarchy = get_or_create_hierarchy(db, ITEM_TYPE, CATEGORY, group["sub_category"])
            source = get_or_create_source(db, buyer, hierarchy, group["gender"], group["category_url"])

            print(f"\n{group['gender'].value} / {group['sub_category']} "
                  f"(sub_category_id={hierarchy.id}, source_config_id={source.id})")

            for name, price, original_price, image_url in group["rows"]:
                code = _code_from_image_url(image_url)
                product_url = _product_url_from_code(code)

                existing = db.query(Product).filter(Product.product_url == product_url).first()
                if existing:
                    print(f"  SKIP (already exists): {name}")
                    total_skipped += 1
                    continue

                db.add(
                    Product(
                        product_uid=str(uuid.uuid4()),
                        source=BRAND.lower(),
                        brand=BRAND,
                        category=group["sub_category"].lower(),
                        subcategory=CATEGORY,
                        sub_category_id=hierarchy.id,
                        source_config_id=source.id,
                        buyer_id=buyer.id,
                        role=SourceRole.BUYER,
                        gender=group["gender"],
                        product_name=name,
                        product_code=code,
                        product_url=product_url,
                        image_url=image_url,
                        price=price,
                        original_price=original_price,
                        currency=CURRENCY,
                        availability="in_stock",
                        scraped_at=datetime.utcnow(),
                    )
                )
                total_inserted += 1
                print(f"  OK: {name} ({CURRENCY} {price})")

        db.commit()
        print(f"\nDone. Inserted {total_inserted} product(s), skipped {total_skipped} already-present.")
    finally:
        db.close()


if __name__ == "__main__":
    import_data()