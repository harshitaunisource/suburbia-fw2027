"""
Seeds the initial "master data" for the buyer/competitor system: two
buyers (Suburbia, Textilon) plus every brand+URL already researched
elsewhere in this project, wired up as GenericSourceConfig rows.

This turns what used to be hardcoded lists (the SCRAPER_CATEGORIES array
in frontend/src/pages/DataCollection.jsx, plus each scraper module's own
CATEGORY_URL_* constants) into real, editable rows -- so from this point
on, adding a category or a competitor is a UI action (or an API call),
not a code change. Nothing here is hardcoded anywhere else afterward;
this script is just how the CURRENT data gets into the database once.

Safe to re-run: skips any (buyer, brand, category_url) combination that
already exists.

Usage:
    cd backend
    python -m scripts.seed_buyers_master_data
"""
import json
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import Buyer, GenericSourceConfig, ItemHierarchy, SourceRole

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "garment_apparel_sources.json"

# Textilon (pajamas) isn't in garment_apparel_sources.json -- it was
# researched separately (see app/scrapers/textilon.py, women_secret.py,
# lupo.py, lili_pink.py docstrings for where each URL came from).
TEXTILON_ROWS = [
    {
        "item_type": "GARMENT", "category": "APPAREL", "sub_category": "Pajamas",
        "brand": "Textilon", "role": SourceRole.BUYER,
        "category_url": "https://bo.textilon.com/articulos/categoria/mujer/subcategoria/pijamas",
        "currency": "USD", "notes": "Textilon's own women's pajamas category.",
    },
    {
        "item_type": "GARMENT", "category": "APPAREL", "sub_category": "Pajamas",
        "brand": "Women'Secret", "role": SourceRole.COMPETITOR,
        "category_url": "https://womensecret.com/es/es/mujer/dormir-y-homewear/pijamas",
        "currency": "EUR", "notes": None,
    },
    {
        "item_type": "GARMENT", "category": "APPAREL", "sub_category": "Pajamas",
        "brand": "Lupo", "role": SourceRole.COMPETITOR,
        "category_url": "https://www.lupo.com.br/feminino/pijamas",
        "currency": "BRL", "notes": None,
    },
    {
        "item_type": "GARMENT", "category": "APPAREL", "sub_category": "Pajamas",
        "brand": "Lili Pink", "role": SourceRole.COMPETITOR,
        "category_url": "https://www.lilipink.com/mujer/pijamas",
        "currency": "USD", "notes": None,
    },
]


def _get_or_create_hierarchy(db, item_type: str, category: str, sub_category: str) -> ItemHierarchy:
    row = (
        db.query(ItemHierarchy)
        .filter(
            ItemHierarchy.item_type == item_type,
            ItemHierarchy.category == category,
            ItemHierarchy.sub_category == sub_category,
        )
        .first()
    )
    if row:
        return row
    row = ItemHierarchy(item_type=item_type, category=category, sub_category=sub_category)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _get_or_create_buyer(db, name: str) -> Buyer:
    buyer = db.query(Buyer).filter(Buyer.name.ilike(name)).first()
    if buyer:
        return buyer
    buyer = Buyer(name=name)
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    return buyer


def seed():
    init_db()
    db = SessionLocal()
    try:
        suburbia = _get_or_create_buyer(db, "Suburbia")
        textilon = _get_or_create_buyer(db, "Textilon")

        existing_keys = {
            (s.buyer_id, s.brand, s.category_url)
            for s in db.query(GenericSourceConfig).all()
        }

        added = 0
        skipped_no_hierarchy = 0

        # ---- Suburbia + its competitors, from garment_apparel_sources.json
        if DATA_FILE.exists():
            with open(DATA_FILE, encoding="utf-8") as f:
                rows = json.load(f)
            for row in rows:
                hierarchy = _get_or_create_hierarchy(
                    db, row["item_type"], row["category"], row["sub_category"]
                )
                role = SourceRole.BUYER if row["brand"] == "Suburbia" else SourceRole.COMPETITOR
                key = (suburbia.id, row["brand"], row["category_url"])
                if key in existing_keys:
                    continue
                db.add(
                    GenericSourceConfig(
                        sub_category_id=hierarchy.id,
                        buyer_id=suburbia.id,
                        role=role,
                        brand=row["brand"],
                        category_url=row["category_url"],
                        currency=row.get("currency", "USD"),
                        notes=row.get("notes"),
                    )
                )
                existing_keys.add(key)
                added += 1
        else:
            print(f"WARNING: {DATA_FILE} not found -- skipping Suburbia competitor import.")

        # ---- Textilon + its competitors
        for row in TEXTILON_ROWS:
            hierarchy = _get_or_create_hierarchy(
                db, row["item_type"], row["category"], row["sub_category"]
            )
            key = (textilon.id, row["brand"], row["category_url"])
            if key in existing_keys:
                continue
            db.add(
                GenericSourceConfig(
                    sub_category_id=hierarchy.id,
                    buyer_id=textilon.id,
                    role=row["role"],
                    brand=row["brand"],
                    category_url=row["category_url"],
                    currency=row.get("currency", "USD"),
                    notes=row.get("notes"),
                )
            )
            existing_keys.add(key)
            added += 1

        db.commit()
        print(f"Seeded {added} new source rows across 2 buyers (Suburbia, Textilon).")
        if skipped_no_hierarchy:
            print(f"Skipped {skipped_no_hierarchy} rows with no matching hierarchy entry.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()