"""
One-off backfill: classifies `products.gender` for every existing row
where it's still NULL. The classic per-brand scrapers (suburbia, zara,
hm, c_and_a, primark, old_navy, shein, boohoo, asos, textilon) never set
this field -- see app/services/gender_classify.py's docstring for the
full story (this is the fix for Primark's girls' blouses showing up
mixed in with ladies' blouses with no way to filter them apart).

New scrapes are classified automatically from now on (see
app/services/ingest.py). This script is only needed once, to backfill
whatever was scraped before that change.

Safe to re-run: only rows with gender IS NULL are touched.

Usage:
    cd backend
    python -m scripts.backfill_product_gender
"""
from sqlalchemy import text

from app.database import SessionLocal, init_db
from app.services.gender_classify import classify_gender


def backfill():
    init_db()
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT id, product_name, category, subcategory FROM products WHERE gender IS NULL")
        ).fetchall()
        if not rows:
            print("No products rows need a gender backfill.")
            return

        print(f"Classifying gender for {len(rows)} existing product row(s)...")
        counts: dict[str, int] = {}
        for row_id, product_name, category, subcategory in rows:
            gender = classify_gender(product_name, category, subcategory)
            counts[gender.value] = counts.get(gender.value, 0) + 1
            db.execute(
                text("UPDATE products SET gender = :gender WHERE id = :id"),
                {"gender": gender.value, "id": row_id},
            )
        db.commit()

        print("Done. Breakdown:")
        for gender_value, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {gender_value}: {count}")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()