"""
Fixes a real deployment bug: the trend-matching feature's tables
(trend_uploads, trend_products, trend_matches) were first created on
your database by an earlier version of this app. Since then, the model
changed twice -- new progress-tracking columns were added to
trend_uploads, and trend_matches.vendor_product_id was renamed to
catalogue_product_id when the vendor-catalogue upload feature was
removed -- but nothing ever ran an ALTER TABLE for those changes.
`Base.metadata.create_all()` (called on every backend startup) only
creates tables that don't exist yet; it never alters a table that's
already there. That mismatch is exactly what caused the live crash:
    psycopg2.errors.UndefinedColumn: column "total_products" of
    relation "trend_uploads" does not exist

Since these tables only ever held data from a first attempt that failed
before completing (the SSL-drop crash from the previous round, then
this column-mismatch crash), there's nothing real to migrate --
simplest and safest fix is to drop them and let them recreate fresh
with the current, correct schema on the next backend start.

Also drops vendor_catalogue_uploads / vendor_catalogue_products and
their old enum type -- leftover from the vendor-catalogue feature that
was removed; nothing in the current code references them anymore.

Usage:
    cd backend
    python -m scripts.reset_trend_matching_schema
"""
from sqlalchemy import text

from app.database import SessionLocal, init_db


def reset():
    db = SessionLocal()
    try:
        print("Dropping trend-matching tables (if they exist)...")
        # Dropped in dependency order (children before parents) so CASCADE
        # isn't needed -- keeps this script portable across Postgres and
        # SQLite (SQLite's DROP TABLE doesn't support the CASCADE keyword).
        for table in [
            "trend_matches",
            "trend_products",
            "trend_uploads",
            "vendor_catalogue_products",
            "vendor_catalogue_uploads",
        ]:
            db.execute(text(f"DROP TABLE IF EXISTS {table}"))
            print(f"  Dropped {table} (if it existed).")

        # Postgres-only: the old enum type (VENDOR/WEB) needs dropping
        # separately, or CREATE TYPE for the new one (CATALOGUE/WEB)
        # collides with it on next startup. No-op on SQLite.
        try:
            db.execute(text("DROP TYPE IF EXISTS trendmatchsourcetype"))
            print("  Dropped old trendmatchsourcetype enum (if it existed).")
        except Exception:
            pass

        db.commit()
        print("Done. Tables will be recreated with the current schema on next backend start.")
    finally:
        db.close()

    # Recreate immediately too, so this works even if you don't restart
    # the backend right after running this script.
    init_db()
    print("Recreated trend-matching tables with the current schema.")


if __name__ == "__main__":
    reset()