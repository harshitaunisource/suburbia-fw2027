"""
One-time migration: adds catalogue_products.source_ref, needed for the
"Add to PPT" cart feature -- lets a checkbox on the Products / Search
Products / Explore Categories pages know whether a given scraped product
is already in the current PPT batch, and toggle it on/off idempotently.

Same reason this can't just be "redeploy and it works" as the two
migrations before it: catalogue_products already exists with real rows
in your database, and SQLAlchemy's create_all() only creates missing
tables, never alters an existing one.

Safe to re-run: checks the column's existence first.

Usage:
    cd backend
    python -m scripts.migrate_add_cart_source_ref
"""
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine, init_db


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    return column_name in [c["name"] for c in inspector.get_columns(table_name)]


def migrate():
    init_db()
    db = SessionLocal()
    try:
        if _column_exists("catalogue_products", "source_ref"):
            print("catalogue_products.source_ref already exists, skipping.")
            return
        print("Adding catalogue_products.source_ref ...")
        db.execute(text("ALTER TABLE catalogue_products ADD COLUMN source_ref VARCHAR(64)"))
        db.commit()
        # Postgres and SQLite both support a plain unique index add
        # after the fact; existing rows are all NULL, which is fine --
        # multiple NULLs don't violate a unique index.
        db.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_catalogue_products_source_ref "
                "ON catalogue_products (source_ref)"
            )
        )
        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()