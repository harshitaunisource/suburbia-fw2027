"""
One-time fix for a common gotcha after migrating data into Postgres with
explicit primary key values (as migrate_to_postgres.py's bulk_insert_
mappings does): Postgres's internal auto-increment sequence for each
table's `id` column does NOT automatically advance to match rows
inserted with explicit ids. The next row created normally (without an
explicit id -- e.g. a new ScrapeRun row from a real scrape) then tries
to reuse an id that's already taken, crashing with:

    psycopg2.errors.UniqueViolation: duplicate key value violates
    unique constraint "scrape_runs_pkey"

This resets every table's sequence to (MAX(id) + 1), which is the
standard, safe fix for this exact situation. Safe to re-run any time.

Usage:
    cd backend
    python -m scripts.fix_postgres_sequences
"""
import os

from dotenv import load_dotenv

load_dotenv()  # picks up backend/.env -- this script previously skipped
# this step, so DATABASE_URL always came back empty even with a valid
# .env file present.

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL")

TABLES = ["products", "product_attributes", "scrape_runs", "product_opportunities", "catalogue_products"]


def fix_sequences(database_url: str):
    if not database_url:
        raise SystemExit("DATABASE_URL is not set.")
    if not database_url.startswith("postgresql"):
        raise SystemExit(
            f"DATABASE_URL doesn't look like Postgres ({database_url.split('://')[0]}://...) -- "
            "this fix is only relevant for Postgres. Nothing to do for SQLite."
        )

    engine = create_engine(database_url)
    with engine.connect() as conn:
        for table in TABLES:
            result = conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )
            )
            new_value = result.scalar()
            print(f"  {table}: sequence reset to {new_value}")
        conn.commit()
    print("\nAll sequences fixed. New rows will now get correct, non-colliding ids.")


if __name__ == "__main__":
    fix_sequences(DATABASE_URL)