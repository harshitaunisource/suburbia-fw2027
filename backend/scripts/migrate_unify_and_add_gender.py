"""
One-time migration for the 2026-09-07 changes:

  1. New columns on `products`: buyer_id, role, sub_category_id,
     source_config_id, gender, pattern, color -- these used to only
     exist on `generic_products`.
  2. New column `gender` on `generic_source_configs`.
  3. New column `link_discovery_strategy` on `generic_scrape_runs`.
  4. Backfills every existing `generic_products` row into `products`
     (skipping any product_url that's already present there), so
     everything previously scraped via Search Products / Explore
     Categories / Add Brand shows up on the classic Products page,
     Market Analytics, and Buyer Opportunities -- which have always
     queried `products`, they just never received these rows.

Safe to re-run: every ALTER is guarded by a column-existence check, and
the backfill only inserts rows whose product_url isn't already in
`products` (checked by URL, since generic_products predates
products.product_uid and the two tables never shared one).

Usage:
    cd backend
    python -m scripts.migrate_unify_and_add_gender
"""
import uuid
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import SessionLocal, engine


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def inspector_has_table(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


NEW_PRODUCT_COLUMNS = [
    ("buyer_id", "INTEGER"),
    ("role", "VARCHAR(20)"),
    ("sub_category_id", "INTEGER"),
    ("source_config_id", "INTEGER"),
    ("gender", "VARCHAR(20)"),
    ("pattern", "VARCHAR(60)"),
    ("color", "VARCHAR(60)"),
]


def migrate():
    db = SessionLocal()
    try:
        # -- products: new unification columns ------------------------------
        for col_name, col_type in NEW_PRODUCT_COLUMNS:
            if not _column_exists("products", col_name):
                print(f"Adding products.{col_name} ...")
                db.execute(text(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}"))
                db.commit()
            else:
                print(f"products.{col_name} already exists, skipping.")

        # -- generic_source_configs.gender -----------------------------------
        if inspector_has_table("generic_source_configs"):
            if not _column_exists("generic_source_configs", "gender"):
                print("Adding generic_source_configs.gender ...")
                db.execute(text("ALTER TABLE generic_source_configs ADD COLUMN gender VARCHAR(20)"))
                db.commit()
            else:
                print("generic_source_configs.gender already exists, skipping.")

        # -- generic_scrape_runs.link_discovery_strategy ----------------------
        if inspector_has_table("generic_scrape_runs"):
            if not _column_exists("generic_scrape_runs", "link_discovery_strategy"):
                print("Adding generic_scrape_runs.link_discovery_strategy ...")
                db.execute(
                    text("ALTER TABLE generic_scrape_runs ADD COLUMN link_discovery_strategy VARCHAR(30)")
                )
                db.commit()
            else:
                print("generic_scrape_runs.link_discovery_strategy already exists, skipping.")

        # -- backfill: generic_products -> products ---------------------------
        if not inspector_has_table("generic_products"):
            print("No generic_products table found -- nothing to backfill.")
            print("\nMigration complete.")
            return

        # generic_products is a pre-existing table (created before this
        # feature) -- it needs the same guarded ALTER as products/
        # generic_source_configs above, or the backfill SELECT below fails
        # with "column gp.gender does not exist" on any live DB where this
        # table was created before Gender was added to the model.
        if not _column_exists("generic_products", "gender"):
            print("Adding generic_products.gender ...")
            db.execute(text("ALTER TABLE generic_products ADD COLUMN gender VARCHAR(20)"))
            db.commit()
        else:
            print("generic_products.gender already exists, skipping.")

        rows = db.execute(text("""
            SELECT gp.id, gp.product_uid, gp.sub_category_id, gp.source_config_id,
                   gp.buyer_id, gp.role, gp.gender, gp.brand, gp.product_name,
                   gp.product_code, gp.product_url, gp.image_url, gp.local_image_path,
                   gp.price, gp.original_price, gp.currency, gp.material, gp.pattern,
                   gp.color, gp.description, gp.scraped_at,
                   h.sub_category, h.category
            FROM generic_products gp
            JOIN item_hierarchy h ON h.id = gp.sub_category_id
            WHERE gp.product_url NOT IN (SELECT product_url FROM products)
        """)).fetchall()

        if not rows:
            print("No generic_products rows need backfilling -- products table already has them all.")
            print("\nMigration complete.")
            return

        print(f"Backfilling {len(rows)} generic_products row(s) into products ...")
        for row in rows:
            (
                _id, product_uid, sub_category_id, source_config_id, buyer_id, role,
                gender, brand, product_name, product_code, product_url, image_url,
                local_image_path, price, original_price, currency, material, pattern,
                color, description, scraped_at, sub_category, category,
            ) = row

            db.execute(
                text("""
                    INSERT INTO products (
                        product_uid, source, brand, category, subcategory,
                        sub_category_id, source_config_id, buyer_id, role, gender,
                        product_name, product_code, product_url, image_url,
                        local_image_path, price, original_price, currency, material,
                        pattern, color, description, image_kind, scraped_at,
                        created_at, updated_at
                    ) VALUES (
                        :product_uid, :source, :brand, :category, :subcategory,
                        :sub_category_id, :source_config_id, :buyer_id, :role, :gender,
                        :product_name, :product_code, :product_url, :image_url,
                        :local_image_path, :price, :original_price, :currency, :material,
                        :pattern, :color, :description, :image_kind, :scraped_at,
                        :created_at, :updated_at
                    )
                """),
                {
                    "product_uid": product_uid or str(uuid.uuid4()),
                    "source": (brand or "unknown").lower().replace(" ", "_"),
                    "brand": brand,
                    "category": (sub_category or "unknown").lower(),
                    "subcategory": category,
                    "sub_category_id": sub_category_id,
                    "source_config_id": source_config_id,
                    "buyer_id": buyer_id,
                    "role": role,
                    "gender": gender,
                    "product_name": product_name,
                    "product_code": product_code,
                    "product_url": product_url,
                    "image_url": image_url,
                    "local_image_path": local_image_path,
                    "price": price,
                    "original_price": original_price,
                    "currency": currency,
                    "material": material,
                    "pattern": pattern,
                    "color": color,
                    "description": description,
                    "image_kind": "COMPETITOR" if role != "BUYER" else "OUR_PRODUCT",
                    "scraped_at": scraped_at or datetime.utcnow(),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                },
            )
        db.commit()
        print(f"Backfilled {len(rows)} row(s).")
        print("\nMigration complete. generic_products is left in place (read-only, "
              "for historical reference) -- new scrapes write directly to products.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()