"""
One-time migration for the buyer/competitor feature, needed because your
generic_source_configs / generic_products tables already existed
(created empty by an earlier run of this app) before buyer_id/role were
added to the model.

Why this can't just be "redeploy and it works": SQLAlchemy's
Base.metadata.create_all() (called at app startup) only CREATES missing
tables -- it never ALTERs an existing table to add a new column. The new
`buyers` table gets created automatically (it didn't exist before), but
generic_source_configs and generic_products already existed, so their
new buyer_id/role columns need to be added explicitly, once, here.

Safe to re-run: checks for each column's existence first (works on both
SQLite and Postgres) and skips anything already applied.

Run this BEFORE scripts.seed_buyers_master_data.

Usage:
    cd backend
    python -m scripts.migrate_add_buyers
"""
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine, init_db


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def migrate():
    # Creates the new `buyers` table (and item_hierarchy / generic_* if
    # this is a brand-new database) -- harmless no-op for tables that
    # already exist.
    init_db()

    db = SessionLocal()
    try:
        # -- generic_source_configs.buyer_id / role -------------------------
        if not _column_exists("generic_source_configs", "buyer_id"):
            print("Adding generic_source_configs.buyer_id ...")
            db.execute(text("ALTER TABLE generic_source_configs ADD COLUMN buyer_id INTEGER"))
            db.commit()
        else:
            print("generic_source_configs.buyer_id already exists, skipping ALTER.")

        if not _column_exists("generic_source_configs", "role"):
            print("Adding generic_source_configs.role (default 'COMPETITOR') ...")
            db.execute(
                text("ALTER TABLE generic_source_configs ADD COLUMN role VARCHAR(20) DEFAULT 'COMPETITOR'")
            )
            db.commit()
        else:
            print("generic_source_configs.role already exists, skipping ALTER.")

        # -- generic_products.buyer_id / role --------------------------------
        if not _column_exists("generic_products", "buyer_id"):
            print("Adding generic_products.buyer_id ...")
            db.execute(text("ALTER TABLE generic_products ADD COLUMN buyer_id INTEGER"))
            db.commit()
        else:
            print("generic_products.buyer_id already exists, skipping ALTER.")

        if not _column_exists("generic_products", "role"):
            print("Adding generic_products.role ...")
            db.execute(text("ALTER TABLE generic_products ADD COLUMN role VARCHAR(20)"))
            db.commit()
        else:
            print("generic_products.role already exists, skipping ALTER.")

        # Any pre-existing generic_source_configs rows (from before buyers
        # existed) have buyer_id = NULL at this point, which the app can't
        # use (every row needs a buyer). There should be none in practice
        # -- this feature had no buyers to attach to before now -- but if
        # any do exist, report them instead of silently leaving them
        # broken or guessing which buyer they belong to.
        orphaned = db.execute(
            text("SELECT id, brand, category_url FROM generic_source_configs WHERE buyer_id IS NULL")
        ).fetchall()
        if orphaned:
            print(
                f"\nWARNING: {len(orphaned)} existing generic_source_configs row(s) have no buyer_id "
                f"and won't be usable until fixed (either delete them or UPDATE ... SET buyer_id = "
                f"... manually):"
            )
            for row_id, brand, url in orphaned:
                print(f"  id={row_id} brand={brand!r} url={url!r}")
        else:
            print("\nNo pre-existing generic_source_configs rows needed a buyer_id fix.")

        print("\nMigration complete. Now run: python -m scripts.seed_buyers_master_data")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()