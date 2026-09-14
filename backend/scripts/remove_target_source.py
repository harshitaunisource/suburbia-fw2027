"""
One-off cleanup: removes every row left over from the "target" scraper,
which has been removed from the app entirely (2026-09-14) -- its category
URLs never actually resolved to the intended women's sweaters/blouses
pages, so the only rows it ever produced were two unrelated
outdoor-furniture listings scraped off the wrong category page.

This does NOT touch any other source's data. Safe to re-run -- every
DELETE is scoped to source='target' (or, for catalogue_products, to
source_ref values pointing at a product that no longer exists after the
first run), so running it again when there's nothing left to delete is a
no-op.

Usage:
    cd backend
    python -m scripts.remove_target_source
"""
from sqlalchemy import text

from app.database import SessionLocal, init_db


def cleanup():
    init_db()
    db = SessionLocal()
    try:
        target_ids = [
            row[0] for row in db.execute(text("SELECT id FROM products WHERE source = 'target'")).fetchall()
        ]
        if target_ids:
            refs = [f"product:{pid}" for pid in target_ids]
            placeholders = ", ".join(f":r{i}" for i in range(len(refs)))
            params = {f"r{i}": ref for i, ref in enumerate(refs)}
            deleted_cart = db.execute(
                text(f"DELETE FROM catalogue_products WHERE source_ref IN ({placeholders})"), params
            ).rowcount
            print(f"Removed {deleted_cart} catalogue_products row(s) referencing target products.")

        deleted_products = db.execute(text("DELETE FROM products WHERE source = 'target'")).rowcount
        print(f"Removed {deleted_products} products row(s) from source='target'.")

        deleted_runs = db.execute(text("DELETE FROM scrape_runs WHERE source = 'target'")).rowcount
        print(f"Removed {deleted_runs} scrape_runs row(s) from source='target'.")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()