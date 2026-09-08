"""
One-off: removes all Zara products (the old India-storefront data)
plus their product_attributes rows (an AI-extracted-attributes table
that references products via a foreign key -- deleting a product
without first deleting its attributes row violates that FK, which is
exactly what happened live), plus its GenericSourceConfig and
GenericScrapeRun rows.

Usage: cd backend && python -m scripts.delete_brand_products
(edit BRAND below if you ever need this for a different brand)
"""
from sqlalchemy import text
from app.database import SessionLocal

BRAND = "Zara"

db = SessionLocal()
try:
    product_count = db.execute(
        text("SELECT count(*) FROM products WHERE brand ILIKE :b"), {"b": BRAND}
    ).scalar()
    source_ids = [
        row[0] for row in db.execute(
            text("SELECT id FROM generic_source_configs WHERE brand ILIKE :b"), {"b": BRAND}
        ).fetchall()
    ]
    print(f"Found {product_count} product(s) and {len(source_ids)} source(s) for brand '{BRAND}'.")

    # Delete dependent product_attributes rows FIRST -- these reference
    # products.id via a foreign key, so deleting the product before its
    # attributes row violates that constraint (confirmed live).
    attr_result = db.execute(
        text(
            "DELETE FROM product_attributes WHERE product_id IN "
            "(SELECT id FROM products WHERE brand ILIKE :b)"
        ),
        {"b": BRAND},
    )
    print(f"Deleted {attr_result.rowcount} product_attributes row(s).")

    db.execute(text("DELETE FROM products WHERE brand ILIKE :b"), {"b": BRAND})
    if source_ids:
        db.execute(
            text("DELETE FROM generic_scrape_runs WHERE source_config_id = ANY(:ids)"),
            {"ids": source_ids},
        )
        db.execute(text("DELETE FROM generic_source_configs WHERE brand ILIKE :b"), {"b": BRAND})
    db.commit()
    print("Done.")
finally:
    db.close()