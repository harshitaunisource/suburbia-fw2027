"""
Seeds the real Item Type / Category / Sub Category hierarchy (from the
uploaded Item_Category_SubCategory_Hierarchy.xlsx, converted once to
data/item_hierarchy.json) into the item_hierarchy table.

Safe to re-run: skips rows that already exist (matched on the exact
item_type + category + sub_category combination).

Starting sanity_keywords are auto-derived from each row's own Sub
Category and Category text (lowercased, split into words, common stop
words removed) -- a reasonable default, NOT hand-verified synonyms,
UNLESS the row already provides its own "sanity_keywords" (as the
current data/item_hierarchy.json does for all 7 rows) -- those are
always preferred over the auto-derived guess. Refine further via the
API (PATCH /api/generic/hierarchy/{id}) as real scraping surfaces
contamination the keywords miss -- same iterative refinement pattern
already used for Suburbia's own category checks.

Usage:
    cd backend
    python -m scripts.seed_item_hierarchy
"""
import json
import re
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import ItemHierarchy

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "item_hierarchy.json"

STOP_WORDS = {"and", "or", "the", "a", "an", "of", "for", "with", "&", "-"}


def derive_keywords(category: str, sub_category: str) -> str:
    text = f"{category} {sub_category}".lower()
    words = re.findall(r"[a-z]+", text)
    keywords = sorted({w for w in words if w not in STOP_WORDS and len(w) > 2})
    return ", ".join(keywords)


def seed():
    if not DATA_FILE.exists():
        raise SystemExit(f"Data file not found: {DATA_FILE}")

    with open(DATA_FILE, encoding="utf-8") as f:
        rows = json.load(f)

    init_db()
    db = SessionLocal()
    try:
        existing = {
            (r.item_type, r.category, r.sub_category) for r in db.query(ItemHierarchy).all()
        }
        added = 0
        for row in rows:
            key = (row["item_type"], row["category"], row["sub_category"])
            if key in existing:
                continue
            db.add(
                ItemHierarchy(
                    item_type=row["item_type"],
                    category=row["category"],
                    sub_category=row["sub_category"],
                    sanity_keywords=row.get("sanity_keywords") or derive_keywords(row["category"], row["sub_category"]),
                )
            )
            added += 1
        db.commit()
        print(f"Seeded {added} new hierarchy rows ({len(existing)} already present, skipped).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()