"""
Bulk-imports researched (item_type, category, sub_category, brand,
category_url) rows into generic_source_configs -- this is where the
output of the separate brand/URL research chat gets loaded in.

Expects a JSON file: a list of objects with these keys:
    item_type, category, sub_category   (must exactly match a row
                                          already seeded by
                                          seed_item_hierarchy.py)
    brand, category_url                 (required)
    currency                            (optional, defaults to "USD")
    pdp_link_pattern                    (optional -- a starting guess is
                                          fine; see generic_scraper.py's
                                          DEFAULT_PDP_LINK_PATTERN if
                                          omitted)
    notes                               (optional)

Rows whose (item_type, category, sub_category) doesn't match any seeded
ItemHierarchy row are skipped and reported, not silently dropped.
Safe to re-run: does not de-duplicate against existing sources for the
same sub-category+brand, so re-importing an updated file after fixing a
few rows will add duplicates -- delete the old ones first if replacing,
or just review for dupes after.

Usage:
    cd backend
    python -m scripts.import_generic_sources path/to/researched_sources.json
"""
import json
import sys

from app.database import SessionLocal, init_db
from app.models import GenericSourceConfig, ItemHierarchy


def import_sources(filepath: str):
    with open(filepath, encoding="utf-8") as f:
        rows = json.load(f)

    init_db()
    db = SessionLocal()
    try:
        hierarchy_lookup = {
            (h.item_type, h.category, h.sub_category): h.id for h in db.query(ItemHierarchy).all()
        }

        imported = 0
        skipped = []
        for row in rows:
            key = (row.get("item_type"), row.get("category"), row.get("sub_category"))
            sub_category_id = hierarchy_lookup.get(key)
            if not sub_category_id:
                skipped.append(row)
                continue
            db.add(
                GenericSourceConfig(
                    sub_category_id=sub_category_id,
                    brand=row["brand"],
                    category_url=row["category_url"],
                    currency=row.get("currency", "USD"),
                    pdp_link_pattern=row.get("pdp_link_pattern"),
                    notes=row.get("notes"),
                )
            )
            imported += 1

        db.commit()
        print(f"Imported {imported} source configs.")
        if skipped:
            print(f"\nSkipped {len(skipped)} rows -- no matching (item_type, category, sub_category) found:")
            for row in skipped[:20]:
                print(f"  {row.get('item_type')} / {row.get('category')} / {row.get('sub_category')}")
            if len(skipped) > 20:
                print(f"  ... and {len(skipped) - 20} more")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m scripts.import_generic_sources path/to/researched_sources.json")
    import_sources(sys.argv[1])