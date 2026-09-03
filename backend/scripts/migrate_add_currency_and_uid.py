"""
One-time migration for two schema changes on ALREADY-POPULATED tables:

  1. products.product_uid       (new, unique, backfilled for existing rows)
  2. catalogue_products.currency (new, defaults to 'USD' for existing rows)

Why this can't just be "redeploy and it works": SQLAlchemy's
Base.metadata.create_all() (called at app startup) only CREATES missing
tables -- it never ALTERs an existing table to add a new column. Since
both `products` and `catalogue_products` already have real data in
production, adding these columns to the model alone would not add them
to the live database; every query touching the new columns would fail
with "column does not exist" until this migration runs once.

Safe to re-run: checks for the column's existence first (works on both
SQLite and Postgres) and skips if already applied. Backfilling
product_uid values is also safe to re-run -- only rows with a NULL
product_uid get a new one assigned.

Usage:
    cd backend
    python -m scripts.migrate_add_currency_and_uid
"""
import uuid

from sqlalchemy import inspect, text

from app.database import SessionLocal, engine


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def migrate():
    db = SessionLocal()
    try:
        # -- products.product_uid ------------------------------------------
        if not _column_exists("products", "product_uid"):
            print("Adding products.product_uid ...")
            db.execute(text("ALTER TABLE products ADD COLUMN product_uid VARCHAR(36)"))
            db.commit()
        else:
            print("products.product_uid already exists, skipping ALTER.")

        rows_needing_uid = db.execute(
            text("SELECT id FROM products WHERE product_uid IS NULL")
        ).fetchall()
        if rows_needing_uid:
            print(f"Backfilling product_uid for {len(rows_needing_uid)} existing product rows...")
            for (row_id,) in rows_needing_uid:
                db.execute(
                    text("UPDATE products SET product_uid = :uid WHERE id = :id"),
                    {"uid": str(uuid.uuid4()), "id": row_id},
                )
            db.commit()
        else:
            print("No products rows need a product_uid backfill.")

        # -- catalogue_products.currency ------------------------------------
        if not _column_exists("catalogue_products", "currency"):
            print("Adding catalogue_products.currency (default 'USD') ...")
            db.execute(text("ALTER TABLE catalogue_products ADD COLUMN currency VARCHAR(10) DEFAULT 'USD'"))
            db.commit()
            print(
                "NOTE: existing catalogue_products rows were defaulted to 'USD'. "
                "If any pre-existing entry's price is actually in a different "
                "currency, update it manually via the Our Products page."
            )
        else:
            print("catalogue_products.currency already exists, skipping ALTER.")

        print("\nMigration complete.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()