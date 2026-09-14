"""
One-off cleanup: removes specific entries from Brand Setup -- both
possible shapes a "brand" can take in this app:
  (a) a Buyer row itself (e.g. a second buyer like "Suburbia Weekend"),
  (b) a GenericSourceConfig row (a brand tracked as a buyer's own
      source or a competitor, e.g. "Walmart" configured under some
      buyer via Add Brand).

For each match, also removes what was scraped through it (GenericProduct
and/or the unified Product table rows via source_config_id, and
GenericScrapeRun rows) so nothing orphaned is left behind -- same
approach as scripts/remove_target_source.py.

Edit BRAND_NAMES below to change what gets removed. Matching is
case-insensitive on Buyer.name / GenericSourceConfig.brand.

Safe to re-run: every DELETE is scoped to a name match, so running it
again when there's nothing left to delete is a no-op.

Usage:
    cd backend
    python -m scripts.remove_brands_from_setup
"""
from sqlalchemy import func, text

from app.database import SessionLocal, init_db

BRAND_NAMES = ["Textilon", "Walmart", "Suburbia Weekend"]


def cleanup():
    init_db()
    db = SessionLocal()
    try:
        lowered = [n.lower() for n in BRAND_NAMES]
        placeholders = ", ".join(f":n{i}" for i in range(len(lowered)))
        params = {f"n{i}": n for i, n in enumerate(lowered)}

        # 1. GenericSourceConfig rows matching by brand name (covers a
        #    brand configured as a buyer's own source OR a competitor).
        config_ids = [
            row[0] for row in db.execute(
                text(f"SELECT id FROM generic_source_configs WHERE lower(brand) IN ({placeholders})"), params
            ).fetchall()
        ]

        # 2. Buyer rows matching by name (covers a brand that's itself a
        #    buyer, e.g. a second/variant brand entry).
        buyer_ids = [
            row[0] for row in db.execute(
                text(f"SELECT id FROM buyers WHERE lower(name) IN ({placeholders})"), params
            ).fetchall()
        ]
        if buyer_ids:
            buyer_placeholders = ", ".join(f":b{i}" for i in range(len(buyer_ids)))
            buyer_params = {f"b{i}": bid for i, bid in enumerate(buyer_ids)}
            config_ids += [
                row[0] for row in db.execute(
                    text(f"SELECT id FROM generic_source_configs WHERE buyer_id IN ({buyer_placeholders})"),
                    buyer_params,
                ).fetchall()
            ]

        config_ids = list(set(config_ids))
        print(f"Found {len(config_ids)} matching source config(s), {len(buyer_ids)} matching buyer(s).")

        if config_ids:
            cfg_placeholders = ", ".join(f":c{i}" for i in range(len(config_ids)))
            cfg_params = {f"c{i}": cid for i, cid in enumerate(config_ids)}

            deleted = db.execute(
                text(f"DELETE FROM products WHERE source_config_id IN ({cfg_placeholders})"), cfg_params
            ).rowcount
            print(f"  Removed {deleted} products row(s).")

            deleted = db.execute(
                text(f"DELETE FROM generic_products WHERE source_config_id IN ({cfg_placeholders})"), cfg_params
            ).rowcount
            print(f"  Removed {deleted} generic_products row(s).")

            deleted = db.execute(
                text(f"DELETE FROM generic_scrape_runs WHERE source_config_id IN ({cfg_placeholders})"), cfg_params
            ).rowcount
            print(f"  Removed {deleted} generic_scrape_runs row(s).")

            deleted = db.execute(
                text(f"DELETE FROM generic_source_configs WHERE id IN ({cfg_placeholders})"), cfg_params
            ).rowcount
            print(f"  Removed {deleted} generic_source_configs row(s).")

        if buyer_ids:
            buyer_placeholders = ", ".join(f":b{i}" for i in range(len(buyer_ids)))
            buyer_params = {f"b{i}": bid for i, bid in enumerate(buyer_ids)}
            deleted = db.execute(
                text(f"DELETE FROM buyers WHERE id IN ({buyer_placeholders})"), buyer_params
            ).rowcount
            print(f"  Removed {deleted} buyers row(s).")

        db.commit()
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    cleanup()