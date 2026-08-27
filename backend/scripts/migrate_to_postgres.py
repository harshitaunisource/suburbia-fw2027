"""
One-time migration: copies everything from your local SQLite database
into a Postgres database (e.g. Neon) so a hosted deployment (Railway +
Vercel) has your real scraped data without re-running any scrapers.

Uses bulk_insert_mappings (one efficient batch statement per table)
instead of per-row merge() -- the earlier per-row version made one
network round-trip per row, which is fine locally but painfully slow
against a real remote Postgres instance with hundreds of rows.

IMPORTANT: this version assumes the TARGET database is empty (a fresh
Neon project, as in this case) -- it does a pure INSERT, not an
insert-or-update. Do not run this twice against the same populated
target; if you need to re-run after a partial/failed migration, either
use a fresh Neon database or truncate the target tables first.

Usage:
    cd backend
    $env:TARGET_DATABASE_URL = "postgresql+psycopg2://user:pass@ep-xxx.neon.tech/dbname"
    python -m scripts.migrate_to_postgres
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    CatalogueProduct,
    Product,
    ProductAttributes,
    ProductOpportunity,
    ScrapeRun,
)

SQLITE_URL = os.getenv("SOURCE_DATABASE_URL", "sqlite:///./suburbia_fw2027.db")
POSTGRES_URL = os.environ.get("TARGET_DATABASE_URL")

# Migration order matters for foreign keys:
#   ProductAttributes.product_id -> Product.id
#   CatalogueProduct.opportunity_id -> ProductOpportunity.id
MODELS_IN_ORDER = [Product, ProductAttributes, ScrapeRun, ProductOpportunity, CatalogueProduct]


def migrate(sqlite_url: str, postgres_url: str):
    if not postgres_url:
        raise SystemExit(
            "TARGET_DATABASE_URL is not set. Example (PowerShell):\n"
            '  $env:TARGET_DATABASE_URL = "postgresql+psycopg2://user:pass@ep-xxx.neon.tech/dbname"'
        )

    sqlite_engine = create_engine(sqlite_url)
    postgres_engine = create_engine(postgres_url)

    Base.metadata.create_all(postgres_engine)  # creates tables if they don't exist yet

    SourceSession = sessionmaker(bind=sqlite_engine)
    TargetSession = sessionmaker(bind=postgres_engine)
    src = SourceSession()
    dst = TargetSession()

    try:
        for model in MODELS_IN_ORDER:
            rows = src.query(model).all()
            print(f"Migrating {len(rows)} rows of {model.__tablename__}...", flush=True)
            if rows:
                mappings = [
                    {c.name: getattr(row, c.name) for c in model.__table__.columns} for row in rows
                ]
                dst.bulk_insert_mappings(model, mappings)
                dst.commit()
            print(f"  done.", flush=True)
        print("\nMigration complete.")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate(SQLITE_URL, POSTGRES_URL)